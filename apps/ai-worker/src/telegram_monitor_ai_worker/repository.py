"""PostgreSQL leasing and relational persistence for inference v3."""

import json
from datetime import timedelta
from typing import Any, cast

import asyncpg
from monitoring_common.contracts import normalize_match_text

from telegram_monitor_ai_worker.models import ClaimedAnalysisJob, JobLeaseLostError


class AnalysisJobRepository:
    """Own durable v3 jobs, pass diagnostics, candidates, and final results."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def lease_next_job(
        self, lease_seconds: int, max_attempts: int, model: str = "MamayLM-Gemma-3-27B-IT"
    ) -> ClaimedAnalysisJob | None:
        """Lease one job and create or resume its durable run."""
        async with self._pool.acquire() as connection, connection.transaction():
            await connection.execute(
                """WITH expired_jobs AS (
                       UPDATE analysis_jobs
                       SET status = 'failed', leased_until = NULL,
                           last_error_kind = 'lease_expired',
                           last_error = 'Lease expired after the final allowed attempt',
                           updated_at = now()
                       WHERE status = 'leased' AND leased_until <= now() AND attempts >= $1
                       RETURNING id
                   )
                   UPDATE analysis_runs AS run
                   SET status = 'failed', failure_kind = 'lease_expired',
                       failure_detail = jsonb_build_object(
                           'message', 'Lease expired after the final allowed attempt'
                       ),
                       completed_at = now()
                   FROM expired_jobs
                   WHERE run.job_id = expired_jobs.id AND run.status = 'running'""",
                max_attempts,
            )
            row = await connection.fetchrow(
                """WITH next_job AS (
                       SELECT id FROM analysis_jobs
                       WHERE attempts < $1
                         AND ((status = 'pending' AND available_at <= now())
                           OR (status = 'leased' AND leased_until <= now()))
                       ORDER BY CASE priority WHEN 'live' THEN 0 ELSE 1 END, available_at, id
                       FOR UPDATE SKIP LOCKED LIMIT 1
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
            run_id = await connection.fetchval(
                """INSERT INTO analysis_runs
                   (job_id, post_revision_id, model_name, pipeline_version)
                   VALUES ($1, $2, $3, 'inference_v3_5_2')
                   ON CONFLICT (job_id) DO UPDATE
                   SET status = 'running', pipeline_version = 'inference_v3_5_2'
                   RETURNING id""",
                row["id"],
                row["post_revision_id"],
                model,
            )
        return ClaimedAnalysisJob(
            id=int(row["id"]),
            post_revision_id=int(row["post_revision_id"]),
            post_text=str(row["content"]),
            priority=str(row["priority"]),
            attempts=int(row["attempts"]),
            run_id=int(run_id),
        )

    async def registry_aliases(self) -> list[dict[str, Any]]:
        """Return all registry aliases used for resolution and monitored filtering."""
        rows = await self._pool.fetch(
            """SELECT entity.id AS entity_id, entity.canonical_name, entity.coarse_type,
                      entity.monitored,
                      alias.alias, alias.normalized_alias
               FROM registry_entities AS entity
               JOIN entity_aliases AS alias ON alias.entity_id = entity.id
               ORDER BY entity.id, alias.id"""
        )
        return [dict(row) for row in rows]

    async def renew_lease(self, job_id: int, lease_seconds: int) -> None:
        """Extend a lease before a potentially slow model request."""
        updated = await self._pool.fetchval(
            """UPDATE analysis_jobs
               SET leased_until = now() + ($2 * interval '1 second'), updated_at = now()
               WHERE id = $1 AND status = 'leased' RETURNING id""",
            job_id,
            lease_seconds,
        )
        if updated is None:
            raise JobLeaseLostError(f"analysis job {job_id} is no longer leased")

    async def set_matches(self, run_id: int, entity_ids: list[int]) -> None:
        """Persist the monitored aliases that admitted this run."""
        await self._pool.execute(
            "UPDATE analysis_runs SET matched_entity_ids = $2 WHERE id = $1",
            run_id,
            entity_ids,
        )

    async def skip(self, job: ClaimedAnalysisJob) -> None:
        """Finish a stale job whose text no longer matches a monitored alias."""
        async with self._pool.acquire() as connection, connection.transaction():
            await self._require_lease(connection, job.id)
            await connection.execute(
                """UPDATE analysis_jobs SET status = 'skipped', leased_until = NULL,
                          completed_at = now(), updated_at = now() WHERE id = $1""",
                job.id,
            )
            await connection.execute(
                """UPDATE analysis_runs
                   SET status = 'filtered_out', failure_kind = 'prefilter_miss',
                          completed_at = now() WHERE id = $1""",
                job.run_id,
            )

    async def record_attempt(
        self,
        run_id: int,
        pass_name: str,
        attempt_kind: str,
        prompt_version: str,
        schema_version: str,
        model: str,
        raw_output: str | None,
        parsed_payload: dict[str, Any] | None,
        sanitized_payload: dict[str, Any] | None,
        status: str,
        failure_kind: str | None,
        errors: list[dict[str, str]],
        sanitization_actions: list[dict[str, Any]],
        duration_ms: int | None,
        finish_reason: str | None = None,
        completion_tokens: int | None = None,
    ) -> None:
        """Persist one raw primary or repair response before continuing."""
        await self._pool.execute(
            """INSERT INTO inference_pass_attempts
               (run_id, pass_name, attempt_kind, prompt_version, schema_version, model_name,
                raw_output, parsed_payload, sanitized_payload, status, failure_kind,
                validation_errors, sanitization_actions, duration_ms, finish_reason,
                completion_tokens)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11,
                       $12::jsonb, $13::jsonb, $14, $15, $16)
               ON CONFLICT (run_id, pass_name, attempt_kind) DO UPDATE
               SET raw_output = EXCLUDED.raw_output, parsed_payload = EXCLUDED.parsed_payload,
                   sanitized_payload = EXCLUDED.sanitized_payload,
                   status = EXCLUDED.status, failure_kind = EXCLUDED.failure_kind,
                   validation_errors = EXCLUDED.validation_errors,
                   sanitization_actions = EXCLUDED.sanitization_actions,
                   duration_ms = EXCLUDED.duration_ms,
                   finish_reason = EXCLUDED.finish_reason,
                   completion_tokens = EXCLUDED.completion_tokens, created_at = now()""",
            run_id,
            pass_name,
            attempt_kind,
            prompt_version,
            schema_version,
            model,
            raw_output,
            json.dumps(parsed_payload) if parsed_payload is not None else None,
            json.dumps(sanitized_payload) if sanitized_payload is not None else None,
            status,
            failure_kind,
            json.dumps(errors),
            json.dumps(sanitization_actions),
            duration_ms,
            finish_reason,
            completion_tokens,
        )

    async def record_pass_diagnostic(
        self,
        *,
        run_id: int,
        pass_name: str,
        raw_primary_output: str | None,
        sanitized_primary_payload: dict[str, Any] | None,
        primary_sanitization_actions: list[dict[str, Any]],
        primary_validation_errors: list[dict[str, str]],
        raw_repair_output: str | None,
        sanitized_repair_payload: dict[str, Any] | None,
        repair_sanitization_actions: list[dict[str, Any]],
        repair_validation_errors: list[dict[str, str]],
        final_validation_status: str,
        final_parsed_payload: dict[str, Any] | None,
        fallback: str | None = None,
        recovery_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Upsert the complete primary-to-repair diagnostic record for one pass."""
        await self._pool.execute(
            """INSERT INTO inference_pass_diagnostics
                (run_id, pass_name, raw_primary_output, sanitized_primary_payload,
                primary_validation_errors, primary_sanitization_actions, raw_repair_output,
                sanitized_repair_payload, repair_sanitization_actions,
                repair_validation_errors, final_validation_status, final_parsed_payload, fallback,
                recovery_metadata)
               VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7, $8::jsonb, $9::jsonb,
                       $10::jsonb, $11, $12::jsonb, $13, $14::jsonb)
               ON CONFLICT (run_id, pass_name) DO UPDATE
               SET raw_primary_output = EXCLUDED.raw_primary_output,
                   sanitized_primary_payload = EXCLUDED.sanitized_primary_payload,
                   primary_validation_errors = EXCLUDED.primary_validation_errors,
                   primary_sanitization_actions = EXCLUDED.primary_sanitization_actions,
                   raw_repair_output = EXCLUDED.raw_repair_output,
                   sanitized_repair_payload = EXCLUDED.sanitized_repair_payload,
                   repair_sanitization_actions = EXCLUDED.repair_sanitization_actions,
                   repair_validation_errors = EXCLUDED.repair_validation_errors,
                   final_validation_status = EXCLUDED.final_validation_status,
                   final_parsed_payload = EXCLUDED.final_parsed_payload,
                   fallback = EXCLUDED.fallback,
                   recovery_metadata = EXCLUDED.recovery_metadata,
                   updated_at = now()""",
            run_id,
            pass_name,
            raw_primary_output,
            json.dumps(sanitized_primary_payload)
            if sanitized_primary_payload is not None
            else None,
            json.dumps(primary_validation_errors),
            json.dumps(primary_sanitization_actions),
            raw_repair_output,
            json.dumps(sanitized_repair_payload) if sanitized_repair_payload is not None else None,
            json.dumps(repair_sanitization_actions),
            json.dumps(repair_validation_errors),
            final_validation_status,
            json.dumps(final_parsed_payload) if final_parsed_payload is not None else None,
            fallback,
            json.dumps(recovery_metadata or {}),
        )

    async def completed_pass_payload(self, run_id: int, pass_name: str) -> dict[str, Any] | None:
        """Return the last validated pass payload so transient retries can resume."""
        value = await self._pool.fetchval(
            """SELECT sanitized_payload FROM inference_pass_attempts
               WHERE run_id = $1 AND pass_name = $2 AND status = 'valid'
               ORDER BY id DESC LIMIT 1""",
            run_id,
            pass_name,
        )
        return cast(dict[str, Any] | None, value)

    async def persist_entities(
        self,
        run_id: int,
        entities: list[dict[str, Any]],
        approved_aliases: set[tuple[int, str]],
    ) -> None:
        """Persist resolved post entities and update candidate review queues."""
        async with self._pool.acquire() as connection, connection.transaction():
            exists = await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM post_entities WHERE run_id = $1)", run_id
            )
            if exists:
                return
            for entity in entities:
                registry_id = cast(int | None, entity.get("registry_entity_id"))
                candidate_id: int | None = None
                if registry_id is None:
                    representative = cast(list[str], entity["mentions"])[0]
                    normalized = normalize_match_text(representative)
                    candidate_id = int(
                        await connection.fetchval(
                            """INSERT INTO candidate_entities
                               (normalized_key, representative_mention, occurrence_count)
                               VALUES ($1, $2, 1)
                               ON CONFLICT (normalized_key) DO UPDATE
                               SET occurrence_count = candidate_entities.occurrence_count + 1,
                                   last_seen_at = now(), updated_at = now()
                               RETURNING id""",
                            normalized,
                            representative,
                        )
                    )
                    entity["candidate_entity_id"] = candidate_id
                await connection.execute(
                    """INSERT INTO post_entities
                       (run_id, local_id, registry_entity_id, candidate_entity_id, monitored,
                        mentions)
                       VALUES ($1, $2, $3, $4, $5, $6::jsonb)""",
                    run_id,
                    entity["id"],
                    registry_id,
                    candidate_id,
                    entity["monitored"],
                    json.dumps(entity["mentions"], ensure_ascii=False),
                )
                if registry_id is not None:
                    for mention in cast(list[str], entity["mentions"]):
                        normalized = normalize_match_text(mention)
                        if (registry_id, normalized) in approved_aliases:
                            continue
                        await connection.execute(
                            """INSERT INTO entity_alias_candidates
                               (entity_id, surface_form, normalized_form)
                               VALUES ($1, $2, $3)
                               ON CONFLICT (entity_id, normalized_form) DO UPDATE
                               SET occurrence_count = entity_alias_candidates.occurrence_count + 1,
                                   last_seen_at = now(), updated_at = now()""",
                            registry_id,
                            mention,
                            normalized,
                        )

    async def complete(
        self,
        job: ClaimedAnalysisJob,
        entities: list[dict[str, Any]],
        claims: list[dict[str, Any]],
        classifications: list[dict[str, Any]],
        final_payload: dict[str, Any],
        run_status: str = "completed",
    ) -> None:
        """Atomically persist claims/classifications and complete the leased job."""
        async with self._pool.acquire() as connection, connection.transaction():
            await self._require_lease(connection, job.id)
            entity_rows = await connection.fetch(
                "SELECT id, local_id FROM post_entities WHERE run_id = $1", job.run_id
            )
            entity_db_ids = {str(row["local_id"]): int(row["id"]) for row in entity_rows}
            claim_db_ids: dict[str, int] = {}
            for claim in claims:
                attribution = cast(dict[str, Any], claim["attribution"])
                source_local_id = cast(str | None, attribution["source_entity_id"])
                claim_id = int(
                    await connection.fetchval(
                        """INSERT INTO claims
                           (run_id, local_id, normalized_text, evidence_text, evidence_start,
                            evidence_end, source_kind, source_post_entity_id, epistemic_status)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id""",
                        job.run_id,
                        claim["id"],
                        claim["normalized_text"],
                        claim["evidence_text"],
                        claim["evidence_start"],
                        claim["evidence_end"],
                        attribution["source_kind"],
                        entity_db_ids.get(source_local_id) if source_local_id else None,
                        claim["epistemic_status"],
                    )
                )
                claim_db_ids[cast(str, claim["id"])] = claim_id
                for local_id in cast(list[str], claim["entity_ids"]):
                    await connection.execute(
                        "INSERT INTO claim_entities (claim_id, post_entity_id) VALUES ($1, $2)",
                        claim_id,
                        entity_db_ids[local_id],
                    )
            for row in classifications:
                await connection.execute(
                    """INSERT INTO claim_target_classifications
                       (claim_id, post_entity_id, stance, rhetoric)
                       VALUES ($1, $2, $3, $4::jsonb)""",
                    claim_db_ids[cast(str, row["claim_id"])],
                    entity_db_ids[cast(str, row["entity_id"])],
                    row["stance"],
                    json.dumps(row["rhetoric"], ensure_ascii=False),
                )
            await connection.execute(
                """UPDATE analysis_runs SET status = $2, final_payload = $3::jsonb,
                          completed_at = now() WHERE id = $1""",
                job.run_id,
                run_status,
                json.dumps(final_payload, ensure_ascii=False),
            )
            await connection.execute(
                """UPDATE analysis_jobs SET status = 'completed', leased_until = NULL,
                          completed_at = now(), last_error_kind = NULL, last_error = NULL,
                          updated_at = now() WHERE id = $1""",
                job.id,
            )

    async def retry_or_fail(
        self, job: ClaimedAnalysisJob, error_kind: str, message: str, max_attempts: int
    ) -> bool:
        """Schedule a transient retry or mark the final attempt failed."""
        retry = job.attempts < max_attempts
        delay = min(5 * (2 ** (job.attempts - 1)), 60)
        status = "pending" if retry else "failed"
        await self._pool.execute(
            """UPDATE analysis_jobs
               SET status = $2, leased_until = NULL, available_at = now() + $3,
                   last_error_kind = $4, last_error = $5, updated_at = now()
               WHERE id = $1 AND status = 'leased'""",
            job.id,
            status,
            timedelta(seconds=delay if retry else 0),
            error_kind,
            message[:1000],
        )
        if not retry:
            await self._fail_run(job.run_id, error_kind, message)
        return retry

    async def fail(self, job: ClaimedAnalysisJob, error_kind: str, message: str) -> None:
        """Mark a non-retriable leased job and its run as failed."""
        await self._pool.execute(
            """UPDATE analysis_jobs SET status = 'failed', leased_until = NULL,
                      last_error_kind = $2, last_error = $3, updated_at = now()
               WHERE id = $1 AND status = 'leased'""",
            job.id,
            error_kind,
            message[:1000],
        )
        await self._fail_run(job.run_id, error_kind, message)

    async def _fail_run(self, run_id: int, error_kind: str, message: str) -> None:
        await self._pool.execute(
            """UPDATE analysis_runs SET status = 'failed', failure_kind = $2,
                      failure_detail = $3::jsonb, completed_at = now() WHERE id = $1""",
            run_id,
            error_kind,
            json.dumps({"message": message[:1000]}),
        )

    @staticmethod
    async def _require_lease(connection: asyncpg.Connection, job_id: int) -> None:
        leased = await connection.fetchval(
            "SELECT id FROM analysis_jobs WHERE id = $1 AND status = 'leased'", job_id
        )
        if leased is None:
            raise JobLeaseLostError(f"analysis job {job_id} is no longer leased")
