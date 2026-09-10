"""Unit tests for PostgreSQL-shaped analysis-job persistence."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from telegram_monitor_ai_worker.models import ClaimedAnalysisJob
from telegram_monitor_ai_worker.repository import AnalysisJobRepository


class FakeConnection:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetchval_result: int | None = 3

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        yield

    async def execute(self, query: str, *args: object) -> None:
        self.executed.append((query, args))

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        self.executed.append((query, args))
        return self.row

    async def fetchval(self, query: str, *args: object) -> int | None:
        self.executed.append((query, args))
        return self.fetchval_result


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[FakeConnection]:
        yield self.connection

    async def execute(self, query: str, *args: object) -> None:
        self.executed.append((query, args))


async def test_repository_leases_live_job_with_source_text() -> None:
    connection = FakeConnection(
        {"id": 3, "post_revision_id": 7, "content": "Пост", "priority": "live", "attempts": 1}
    )
    repository = AnalysisJobRepository(FakePool(connection))  # type: ignore[arg-type]

    job = await repository.lease_next_job(300, 3)

    assert job == ClaimedAnalysisJob(3, 7, "Пост", "live", 1)
    lease_query = connection.executed[1][0]
    assert "FOR UPDATE SKIP LOCKED" in lease_query
    assert "CASE priority WHEN 'live' THEN 0 ELSE 1 END" in lease_query


async def test_repository_completes_with_immutable_json_payload() -> None:
    connection = FakeConnection()
    repository = AnalysisJobRepository(FakePool(connection))  # type: ignore[arg-type]
    job = ClaimedAnalysisJob(3, 7, "Пост", "live", 1)

    await repository.complete(job, {"schema_version": "extraction_schema_v1"}, "prompt-v1", "model")

    assert "status = 'completed'" in connection.executed[0][0]
    insert_query, insert_args = connection.executed[1]
    assert "INSERT INTO post_analysis_extractions" in insert_query
    assert insert_args[0] == 7
    assert insert_args[2:] == ("prompt-v1", "model")


async def test_repository_schedules_retry_then_terminal_failure() -> None:
    pool = FakePool(FakeConnection())
    repository = AnalysisJobRepository(pool)  # type: ignore[arg-type]

    retry = await repository.retry_or_fail(
        ClaimedAnalysisJob(3, 7, "Пост", "live", 1), "provider_transient", "down", 3
    )
    terminal = await repository.retry_or_fail(
        ClaimedAnalysisJob(3, 7, "Пост", "live", 3), "provider_transient", "down", 3
    )
    await repository.fail(ClaimedAnalysisJob(4, 8, "Пост", "live", 1), "invalid", "bad JSON")

    assert retry is True
    assert terminal is False
    assert pool.executed[0][1][1] == "pending"
    assert pool.executed[1][1][1] == "failed"
    assert "status = 'failed'" in pool.executed[2][0]
