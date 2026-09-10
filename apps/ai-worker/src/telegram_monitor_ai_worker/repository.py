"""PostgreSQL leasing and result persistence for post-analysis jobs."""

import json
from datetime import timedelta
from typing import Any

import asyncpg

from telegram_monitor_ai_worker.models import ClaimedAnalysisJob, JobLeaseLostError


class AnalysisJobRepository:
    """Own durable analysis-job state and immutable candidate results."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def lease_next_job(
        self, lease_seconds: int, max_attempts: int
    ) -> ClaimedAnalysisJob | None:
        """Lease one available job, prioritizing live collection over backfill."""
        async with self._pool.acquire() as connection, connection.transaction():
            await connection.execute(
                """UPDATE analysis_jobs
                   SET status = 'failed', leased_until = NULL, last_error_kind = 'lease_expired',
                       last_error = 'Lease expired after the final allowed attempt',
                       updated_at = now()
                   WHERE status = 'leased' AND leased_until <= now() AND attempts >= $1""",
                max_attempts,
            )
            row = await connection.fetchrow(
                """WITH next_job AS (
                       SELECT id FROM analysis_jobs
                       WHERE attempts < $1
                         AND ((status = 'pending' AND available_at <= now())
                           OR (status = 'leased' AND leased_until <= now()))
                       ORDER BY CASE priority WHEN 'live' THEN 0 ELSE 1 END, available_at, id
                       FOR UPDATE SKIP LOCKED
                       LIMIT 1
                   )
                   UPDATE analysis_jobs AS job
                   SET status = 'leased', attempts = job.attempts + 1,
                       leased_until = now() + ($2 * interval '1 second'), updated_at = now()
                   FROM next_job, post_revisions AS revision
                   WHERE job.id = next_job.id AND revision.id = job.post_revision_id
                   RETURNING job.id, job.post_revision_id, revision.content, job.priority,
                             job.attempts""",
                max_attempts,
                lease_seconds,
            )
        if row is None:
            return None
        return ClaimedAnalysisJob(
            id=int(row["id"]),
            post_revision_id=int(row["post_revision_id"]),
            post_text=str(row["content"]),
            priority=str(row["priority"]),
            attempts=int(row["attempts"]),
        )

    async def complete(
        self, job: ClaimedAnalysisJob, payload: dict[str, Any], prompt_version: str, model: str
    ) -> None:
        """Atomically save a validated extraction and mark its leased job complete."""
        async with self._pool.acquire() as connection, connection.transaction():
            updated = await connection.fetchval(
                """UPDATE analysis_jobs
                   SET status = 'completed', leased_until = NULL, completed_at = now(),
                       last_error_kind = NULL, last_error = NULL, updated_at = now()
                   WHERE id = $1 AND status = 'leased' AND leased_until > now()
                   RETURNING id""",
                job.id,
            )
            if updated is None:
                raise JobLeaseLostError(f"analysis job {job.id} is no longer leased")
            await connection.execute(
                """INSERT INTO post_analysis_extractions
                   (post_revision_id, payload, prompt_version, model_name)
                   VALUES ($1, $2::jsonb, $3, $4)""",
                job.post_revision_id,
                json.dumps(payload),
                prompt_version,
                model,
            )

    async def retry_or_fail(
        self, job: ClaimedAnalysisJob, error_kind: str, message: str, max_attempts: int
    ) -> bool:
        """Schedule a transient retry or mark the final attempt failed.

        Returns:
            True when the job was rescheduled, false when it reached terminal failure.
        """
        retry = job.attempts < max_attempts
        delay = min(5 * (2 ** (job.attempts - 1)), 60)
        status = "pending" if retry else "failed"
        available_at = timedelta(seconds=delay) if retry else timedelta()
        await self._pool.execute(
            """UPDATE analysis_jobs
               SET status = $2, leased_until = NULL, available_at = now() + $3,
                   last_error_kind = $4, last_error = $5, updated_at = now()
               WHERE id = $1 AND status = 'leased'""",
            job.id,
            status,
            available_at,
            error_kind,
            message[:1000],
        )
        return retry

    async def fail(self, job: ClaimedAnalysisJob, error_kind: str, message: str) -> None:
        """Mark a non-retriable leased job as terminally failed."""
        await self._pool.execute(
            """UPDATE analysis_jobs
               SET status = 'failed', leased_until = NULL, last_error_kind = $2, last_error = $3,
                   updated_at = now()
               WHERE id = $1 AND status = 'leased'""",
            job.id,
            error_kind,
            message[:1000],
        )
