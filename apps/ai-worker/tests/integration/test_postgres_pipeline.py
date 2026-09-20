"""Opt-in PostgreSQL smoke test for the durable inference pipeline."""

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import asyncpg
import pytest
from telegram_monitor_ai_worker.main import AiWorkerSettings, AnalysisWorker
from telegram_monitor_ai_worker.models import ModelResponse
from telegram_monitor_ai_worker.repository import AnalysisJobRepository

POSTGRES_DSN = os.getenv("INTEGRATION_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(not POSTGRES_DSN, reason="INTEGRATION_POSTGRES_DSN is not set")


class FakeInferenceClient:
    """Provide a complete deterministic v3 response without an external model call."""

    async def infer(self, pass_name: str, request: dict[str, Any]) -> ModelResponse:
        source = str(request.get("post_text", "Шабунін працює."))
        responses = {
            "entities": {"entities": [{"mentions": ["Шабунін"]}]},
            "claims": {
                "claims": [
                    {
                        "normalized_text": source,
                        "entity_ids": ["e1"],
                        "evidence_text": source,
                        "attribution": {
                            "source_kind": "channel_editorial",
                            "source_entity_id": None,
                        },
                        "epistemic_status": "ствердження",
                    }
                ]
            },
            "classification": {
                "classifications": [
                    {
                        "claim_id": "c1",
                        "entity_id": "e1",
                        "stance": "відсутнє",
                        "rhetoric": [],
                    }
                ]
            },
        }
        return ModelResponse(json.dumps(responses[pass_name], ensure_ascii=False), 1)

    async def repair(
        self, pass_name: str, original_raw: str, errors: list[dict[str, str]]
    ) -> ModelResponse:
        raise AssertionError(f"unexpected repair for {pass_name}: {original_raw} {errors}")


async def test_postgres_job_reaches_all_durable_inference_tables() -> None:
    """Run a fake model response through actual PostgreSQL leasing and persistence."""
    assert POSTGRES_DSN is not None
    pool = await asyncpg.create_pool(POSTGRES_DSN)
    raw_post_id: int | None = None
    try:
        channel_id = int(
            await pool.fetchval("SELECT id FROM monitored_channels ORDER BY id LIMIT 1")
        )
        raw_post_id = int(
            await pool.fetchval(
                """INSERT INTO raw_posts (channel_id, telegram_message_id, published_at)
                   VALUES ($1, $2, $3) RETURNING id""",
                channel_id,
                -int(datetime.now(UTC).timestamp()),
                datetime.now(UTC),
            )
        )
        revision_id = int(
            await pool.fetchval(
                """INSERT INTO post_revisions (raw_post_id, revision_number, content)
                   VALUES ($1, 1, 'Шабунін працює.') RETURNING id""",
                raw_post_id,
            )
        )
        await pool.execute(
            """INSERT INTO analysis_jobs (post_revision_id, priority, trigger_kind)
               VALUES ($1, 'live', 'manual')""",
            revision_id,
        )
        worker = AnalysisWorker(
            AnalysisJobRepository(pool),
            FakeInferenceClient(),  # type: ignore[arg-type]
            AiWorkerSettings(litellm_api_key="test"),
            logging.getLogger("postgres-smoke"),
        )

        assert await worker.process_next() is True
        counts = await pool.fetchrow(
            """SELECT
                   (SELECT count(*) FROM analysis_runs WHERE post_revision_id = $1) AS runs,
                   (SELECT count(*) FROM post_entities WHERE run_id IN (
                       SELECT id FROM analysis_runs WHERE post_revision_id = $1
                   )) AS entities,
                   (SELECT count(*) FROM claims WHERE run_id IN (
                       SELECT id FROM analysis_runs WHERE post_revision_id = $1
                   )) AS claims,
                   (SELECT count(*) FROM claim_target_classifications WHERE claim_id IN (
                       SELECT id FROM claims WHERE run_id IN (
                           SELECT id FROM analysis_runs WHERE post_revision_id = $1
                       )
                   )) AS classifications""",
            revision_id,
        )
        assert dict(counts) == {"runs": 1, "entities": 1, "claims": 1, "classifications": 1}
    finally:
        if raw_post_id is not None:
            await pool.execute(
                """DELETE FROM analysis_runs WHERE post_revision_id IN (
                       SELECT id FROM post_revisions WHERE raw_post_id = $1
                   )""",
                raw_post_id,
            )
            await pool.execute(
                """DELETE FROM analysis_jobs WHERE post_revision_id IN (
                       SELECT id FROM post_revisions WHERE raw_post_id = $1
                   )""",
                raw_post_id,
            )
            await pool.execute("DELETE FROM post_revisions WHERE raw_post_id = $1", raw_post_id)
            await pool.execute(
                "DELETE FROM raw_posts WHERE id = $1",
                raw_post_id,
            )
        await pool.close()
