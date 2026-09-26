"""PostgreSQL-shaped persistence tests for inference v3."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from telegram_monitor_ai_worker.models import ClaimedAnalysisJob
from telegram_monitor_ai_worker.repository import AnalysisJobRepository, retry_delay


def test_retry_delay_uses_fast_attempts_then_capped_background_schedule() -> None:
    assert retry_delay(job_id=3, attempts=1, retry_round=0, fast_attempts=3).total_seconds() == 5
    assert retry_delay(job_id=3, attempts=2, retry_round=0, fast_attempts=3).total_seconds() == 10

    scheduled = [
        retry_delay(job_id=3, attempts=3 + retry_round, retry_round=retry_round, fast_attempts=3)
        for retry_round in range(6)
    ]
    bases = [300, 1_800, 7_200, 21_600, 86_400, 86_400]

    for delay, base in zip(scheduled, bases, strict=True):
        assert base <= delay.total_seconds() <= base * 1.1
    assert scheduled[-1] == scheduled[-2]


class FakeConnection:
    """Small query-aware asyncpg connection fake."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.lease_row: dict[str, Any] | None = {
            "id": 3,
            "post_revision_id": 7,
            "content": "Шабунін",
            "priority": "live",
            "attempts": 1,
            "retry_round": 0,
        }
        self.post_entities_exist = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        yield

    async def execute(self, query: str, *args: object) -> None:
        self.executed.append((query, args))

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        self.executed.append((query, args))
        if "UPDATE analysis_jobs AS job" in query:
            return self.lease_row
        return None

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        self.executed.append((query, args))
        if "FROM post_entities" in query:
            return [{"id": 20, "local_id": "e1"}]
        return []

    async def fetchval(self, query: str, *args: object) -> object:
        self.executed.append((query, args))
        if "INSERT INTO analysis_runs" in query:
            return 9
        if "SELECT EXISTS" in query:
            return self.post_entities_exist
        if "INSERT INTO candidate_entities" in query:
            return 30
        if "INSERT INTO claims" in query:
            return 40
        if "SELECT sanitized_payload" in query:
            return {"claims": []}
        return 3


class FakePool:
    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[FakeConnection]:
        yield self.connection

    async def execute(self, query: str, *args: object) -> None:
        self.executed.append((query, args))

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        return [
            {
                "entity_id": 10,
                "canonical_name": "Віталій Шабунін",
                "monitored": True,
                "alias": "Шабунін",
                "normalized_alias": "шабунін",
            }
        ]

    async def fetchval(self, query: str, *args: object) -> object:
        self.executed.append((query, args))
        if "SELECT sanitized_payload" in query:
            return {"entities": []}
        return 3


async def test_repository_leases_job_and_creates_durable_run() -> None:
    pool = FakePool()
    repository = AnalysisJobRepository(pool)  # type: ignore[arg-type]

    job = await repository.lease_next_job(300, 3, "model")

    assert job == ClaimedAnalysisJob(3, 7, "Шабунін", "live", 1, 9, 0)
    assert "FOR UPDATE SKIP LOCKED" in pool.connection.executed[1][0]
    assert "INSERT INTO analysis_runs" in pool.connection.executed[2][0]


async def test_repository_finalizes_expired_job_run_before_leasing() -> None:
    pool = FakePool()
    repository = AnalysisJobRepository(pool)  # type: ignore[arg-type]

    await repository.lease_next_job(300, 3, "model")

    expiry_query = pool.connection.executed[0][0]
    assert "WITH expired_jobs" in expiry_query
    assert "UPDATE analysis_runs AS run" in expiry_query
    assert "failure_kind = 'lease_expired'" in expiry_query


async def test_repository_reads_aliases_cached_pass_and_renews_lease() -> None:
    pool = FakePool()
    repository = AnalysisJobRepository(pool)  # type: ignore[arg-type]

    aliases = await repository.registry_aliases()
    cached = await repository.completed_pass_payload(9, "entities")
    await repository.renew_lease(3, 1, 300)
    await repository.set_matches(9, [10])

    assert aliases[0]["normalized_alias"] == "шабунін"
    assert cached == {"entities": []}
    assert len(pool.executed) == 3


async def test_repository_persists_resolved_and_candidate_entities_once() -> None:
    pool = FakePool()
    repository = AnalysisJobRepository(pool)  # type: ignore[arg-type]
    entities = [
        {
            "id": "e1",
            "mentions": ["Шабунін", "глава ЦПК"],
            "registry_entity_id": 10,
            "canonical_name": "Віталій Шабунін",
            "monitored": True,
        },
        {
            "id": "e2",
            "mentions": ["Олег Постернак"],
            "registry_entity_id": None,
            "canonical_name": None,
            "monitored": False,
        },
    ]

    await repository.persist_entities(9, entities, {(10, "шабунін")})

    queries = [query for query, _ in pool.connection.executed]
    assert sum("INSERT INTO post_entities" in query for query in queries) == 2
    assert any("INSERT INTO candidate_entities" in query for query in queries)
    assert any("INSERT INTO entity_alias_candidates" in query for query in queries)
    assert entities[1]["candidate_entity_id"] == 30


async def test_repository_completes_relational_result_and_job() -> None:
    pool = FakePool()
    repository = AnalysisJobRepository(pool)  # type: ignore[arg-type]
    job = ClaimedAnalysisJob(3, 7, "Шабунін", "live", 1, 9)
    claims = [
        {
            "id": "c1",
            "normalized_text": "Шабунін працює.",
            "entity_ids": ["e1"],
            "evidence_text": "Шабунін",
            "evidence_start": 0,
            "evidence_end": 7,
            "attribution": {"source_kind": "channel_editorial", "source_entity_id": None},
            "epistemic_status": "ствердження",
        }
    ]
    classifications = [{"claim_id": "c1", "entity_id": "e1", "stance": "відсутнє", "rhetoric": []}]

    await repository.complete(
        job, [], claims, classifications, {"pipeline_version": "inference_v3_2"}
    )

    queries = [query for query, _ in pool.connection.executed]
    assert any("INSERT INTO claims" in query for query in queries)
    assert any("INSERT INTO claim_target_classifications" in query for query in queries)
    assert any("status = 'completed'" in query for query in queries)


async def test_repository_records_attempt_skip_retry_and_failure() -> None:
    pool = FakePool()
    repository = AnalysisJobRepository(pool)  # type: ignore[arg-type]
    job = ClaimedAnalysisJob(3, 7, "Шабунін", "live", 1, 9)

    await repository.record_attempt(
        9,
        "entities",
        "primary",
        "prompt",
        "schema",
        "model",
        "{}",
        {},
        {},
        "valid",
        None,
        [],
        [],
        5,
    )
    await repository.record_pass_diagnostic(
        run_id=9,
        pass_name="entities",
        raw_primary_output="{}",
        sanitized_primary_payload={},
        primary_sanitization_actions=[],
        primary_validation_errors=[],
        raw_repair_output=None,
        sanitized_repair_payload=None,
        repair_sanitization_actions=[],
        repair_validation_errors=[],
        final_validation_status="valid",
        final_parsed_payload={},
    )
    await repository.skip(job)
    retry_job = ClaimedAnalysisJob(3, 7, "Шабунін", "live", 3, 9, 0)
    assert await repository.retry_or_fail(retry_job, "provider_transient", "down", 3) is True

    assert any("inference_pass_attempts" in query for query, _ in pool.executed)
    assert any("inference_pass_diagnostics" in query for query, _ in pool.executed)
    assert any("status = 'skipped'" in query for query, _ in pool.connection.executed)
    retry_query, retry_args = pool.executed[-2]
    assert "status = $2" in retry_query
    assert retry_args[1] == "retry_scheduled"
    assert retry_args[2] == retry_delay(job_id=3, attempts=3, retry_round=0, fast_attempts=3)
    run_query, run_args = pool.executed[-1]
    assert "status = 'retry_scheduled'" in run_query
    assert run_args == (9, "provider_transient", "down")
