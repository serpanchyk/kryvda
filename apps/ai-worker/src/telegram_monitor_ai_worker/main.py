"""Leased PostgreSQL worker for the three-pass inference-v3 pipeline."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol

import asyncpg
from monitoring_common.config import BaseServiceSettings
from monitoring_common.contracts import (
    SCHEMA_VERSIONS,
    InferenceValidationError,
    PassName,
    parse_json_object,
    sanitize_pass_payload_with_actions,
    validate_pass,
    validation_errors,
)
from monitoring_common.logging import setup_logging
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from telegram_monitor_ai_worker.client import LiteLlmInferenceClient
from telegram_monitor_ai_worker.models import (
    ClaimedAnalysisJob,
    JobLeaseLostError,
    ModelOutputError,
    ModelResponse,
)
from telegram_monitor_ai_worker.pipeline import (
    assign_claim_ids,
    classification_batches,
    classification_items,
    classification_subset,
    final_payload,
    matched_monitored_entity_ids,
    prefilter_entity_groups,
    resolve_entity_groups,
    salvage_classification_objects,
)
from telegram_monitor_ai_worker.prompt import PROMPT_VERSIONS
from telegram_monitor_ai_worker.repository import AnalysisJobRepository


class AiWorkerSettings(BaseServiceSettings):
    """Settings owned by the AI analysis boundary."""

    service_name: str = "telegram-monitor-ai-worker"
    litellm_base_url: str = "http://litellm:4000"
    litellm_api_key: str = ""
    analysis_model: str = "MamayLM-Gemma-3-27B-IT"
    analysis_poll_interval_seconds: int = 5
    analysis_lease_seconds: int = 300
    analysis_request_timeout_seconds: int = 120
    analysis_max_output_tokens: int = 4096
    analysis_max_attempts: int = 3
    analysis_classification_batch_size: int = 5


class InferenceClient(Protocol):
    """Model boundary used by worker orchestration."""

    async def infer(self, pass_name: PassName, request: dict[str, Any]) -> ModelResponse:
        """Return one primary raw pass response."""

    async def repair(
        self, pass_name: PassName, original_raw: str, errors: list[dict[str, str]]
    ) -> ModelResponse:
        """Return one contract-repair response."""


class AnalysisWorker:
    """Lease, execute, validate, and finalize one v3 job at a time."""

    def __init__(
        self,
        repository: AnalysisJobRepository,
        client: InferenceClient,
        settings: AiWorkerSettings,
        logger: logging.Logger,
    ) -> None:
        self._repository = repository
        self._client = client
        self._settings = settings
        self._logger = logger

    async def process_next(self) -> bool:
        """Process one available job and return whether a job was claimed."""
        job = await self._repository.lease_next_job(
            self._settings.analysis_lease_seconds,
            self._settings.analysis_max_attempts,
            self._settings.analysis_model,
        )
        if job is None:
            return False
        self._logger.info("analysis job leased", extra=self._job_log_fields(job))
        try:
            await self._process(job)
        except Exception as error:
            await self._handle_execution_error(job, error)
            return True
        self._logger.info("analysis job completed", extra=self._job_log_fields(job))
        return True

    async def _process(self, job: ClaimedAnalysisJob) -> None:
        aliases = await self._repository.registry_aliases()
        matched_ids = matched_monitored_entity_ids(job.post_text, aliases)
        await self._repository.set_matches(job.run_id, matched_ids)
        if not matched_ids:
            await self._repository.skip(job)
            return

        fallback_groups = prefilter_entity_groups(job.post_text, aliases)
        entity_fallback = False
        try:
            entity_payload = await self._execute_pass(
                job, "entities", {"post_text": job.post_text}, source_text=job.post_text
            )
            model_groups = entity_payload["entities"]
        except (InferenceValidationError, ModelOutputError):
            entity_fallback = True
            model_groups = []
            await self._repository.record_pass_diagnostic(
                run_id=job.run_id,
                pass_name="entities",
                raw_primary_output=None,
                sanitized_primary_payload=None,
                primary_sanitization_actions=[],
                primary_validation_errors=[],
                raw_repair_output=None,
                sanitized_repair_payload=None,
                repair_sanitization_actions=[],
                repair_validation_errors=[],
                final_validation_status="degraded",
                final_parsed_payload={"entities": fallback_groups},
                fallback="prefilter_entities_only",
            )
        entities = resolve_entity_groups([*fallback_groups, *model_groups], aliases)
        approved_aliases = {
            (int(alias["entity_id"]), str(alias["normalized_alias"])) for alias in aliases
        }
        await self._repository.persist_entities(job.run_id, entities, approved_aliases)

        claim_payload = await self._execute_pass(
            job,
            "claims",
            {"post_text": job.post_text, "entities": entities},
            source_text=job.post_text,
            entities=entities,
        )
        claims = assign_claim_ids(claim_payload, job.post_text)
        items = classification_items(job.post_text, entities, claims)
        if items:
            classifications, classification_partial = await self._execute_classification(
                job, items, entities, claims
            )
        else:
            classifications = []
            classification_partial = False
            await self._repository.record_pass_diagnostic(
                run_id=job.run_id,
                pass_name="classification",
                raw_primary_output=None,
                sanitized_primary_payload={"classifications": []},
                primary_sanitization_actions=[],
                primary_validation_errors=[],
                raw_repair_output=None,
                sanitized_repair_payload=None,
                repair_sanitization_actions=[],
                repair_validation_errors=[],
                final_validation_status="valid",
                final_parsed_payload={"classifications": []},
            )
        run_status = (
            "completed_with_partial_classification"
            if classification_partial
            else "completed_with_entity_fallback"
            if entity_fallback
            else "completed"
        )
        degradations = []
        if entity_fallback:
            degradations.append({"pass": "entities", "fallback": "prefilter_entities_only"})
        if classification_partial:
            degradations.append({"pass": "classification", "status": "partial"})
        result = final_payload(entities, claims, classifications, run_status, degradations)
        await self._repository.complete(
            job, entities, claims, classifications, result, run_status=run_status
        )

    async def _execute_classification(
        self,
        job: ClaimedAnalysisJob,
        items: list[dict[str, Any]],
        entities: Sequence[Mapping[str, Any]],
        claims: Sequence[Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], bool]:
        """Classify bounded batches and degrade only pairs that cannot be recovered."""
        rows: list[dict[str, Any]] = []
        expected = [(item["claim_id"], item["entity_id"]) for item in items]
        missing = list(expected)
        history: list[dict[str, Any]] = []
        primary_pairs: list[tuple[str, str]] = []
        salvaged_pairs: list[tuple[str, str]] = []
        retried_pairs: list[tuple[str, str]] = []

        async def run_batches(candidate_items: list[dict[str, Any]], kind: str) -> None:
            nonlocal missing
            batches = classification_batches(
                candidate_items, self._settings.analysis_classification_batch_size
            )
            for batch_index, batch in enumerate(batches, start=1):
                requested = [(item["claim_id"], item["entity_id"]) for item in batch]
                response: ModelResponse | None = None
                payload: dict[str, Any] | None = None
                errors: list[dict[str, str]] = []
                actions: list[dict[str, Any]] = []
                salvaged: list[dict[str, Any]] = []
                recovered: list[dict[str, Any]] = []
                try:
                    await self._repository.renew_lease(
                        job.id, self._settings.analysis_lease_seconds
                    )
                    response = await self._client.infer("classification", {"items": batch})
                    try:
                        payload = parse_json_object(response.raw_output)
                    except InferenceValidationError as error:
                        errors = validation_errors(error)
                        objects = salvage_classification_objects(response.raw_output)
                        salvaged, _, actions = classification_subset(
                            {"classifications": objects}, entities, claims
                        )
                        salvaged = [
                            row
                            for row in salvaged
                            if (row["claim_id"], row["entity_id"]) in requested
                        ]
                        if objects or response.finish_reason in {"length", "max_tokens"}:
                            errors.append(
                                {
                                    "kind": "generation_truncation",
                                    "message": "recovered complete classification-object prefix",
                                }
                            )
                    else:
                        recovered, _, actions = classification_subset(payload, entities, claims)
                        recovered = [
                            row
                            for row in recovered
                            if (row["claim_id"], row["entity_id"]) in requested
                        ]
                    accepted = [*recovered, *salvaged]
                    accepted_pairs = {(row["claim_id"], row["entity_id"]) for row in accepted}
                    errors.extend(
                        {
                            "kind": "missing_pair",
                            "message": f"missing pair: {pair[0]}/{pair[1]}",
                        }
                        for pair in requested
                        if pair not in accepted_pairs
                    )
                    rows.extend(accepted)
                    missing = [pair for pair in missing if pair not in accepted_pairs]
                    if kind == "batch_primary":
                        primary_pairs.extend(accepted_pairs)
                        salvaged_pairs.extend(
                            (row["claim_id"], row["entity_id"]) for row in salvaged
                        )
                    else:
                        retried_pairs.extend(accepted_pairs)
                    await self._record_attempt(
                        job,
                        "classification",
                        kind,
                        response,
                        payload,
                        {"classifications": accepted},
                        "valid" if not errors else "invalid",
                        errors,
                        actions,
                    )
                except ModelOutputError as error:
                    errors = [{"kind": "generation_failure", "message": str(error)}]
                    await self._record_generation_failure(job, "classification", kind, error)
                history.append(
                    {
                        "attempt_kind": kind,
                        "batch_index": batch_index,
                        "requested_pairs": [list(pair) for pair in requested],
                        "raw_output": response.raw_output if response else None,
                        "parsed_output": payload,
                        "salvaged_objects": salvaged,
                        "validation_errors": errors,
                    }
                )

        await run_batches(items, "batch_primary")
        retry_items = [item for item in items if (item["claim_id"], item["entity_id"]) in missing]
        if retry_items:
            await run_batches(retry_items, "batch_retry")
        for item in [item for item in items if (item["claim_id"], item["entity_id"]) in missing]:
            await run_batches([item], "individual_retry")
        await self._repository.record_pass_diagnostic(
            run_id=job.run_id,
            pass_name="classification",
            raw_primary_output=None,
            sanitized_primary_payload={"classifications": rows},
            primary_sanitization_actions=[],
            primary_validation_errors=[],
            raw_repair_output=None,
            sanitized_repair_payload=None,
            repair_sanitization_actions=[],
            repair_validation_errors=[],
            final_validation_status="partial" if missing else "valid",
            final_parsed_payload={"classifications": rows},
            recovery_metadata={
                "expected_pairs": [list(pair) for pair in expected],
                "primary_valid_pairs": [list(pair) for pair in primary_pairs],
                "salvaged_pairs": [list(pair) for pair in salvaged_pairs],
                "retried_pairs": [list(pair) for pair in retried_pairs],
                "permanently_failed_pairs": [list(pair) for pair in missing],
                "final_validation_errors": [
                    {"kind": "missing_pair", "message": f"unclassified pair: {pair[0]}/{pair[1]}"}
                    for pair in missing
                ],
                "attempts": history,
            },
        )
        return rows, bool(missing)

    async def _execute_pass(
        self,
        job: ClaimedAnalysisJob,
        pass_name: PassName,
        request: dict[str, Any],
        source_text: str,
        entities: Sequence[Mapping[str, Any]] = (),
        claims: Sequence[Mapping[str, Any]] = (),
        post_validate: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        completed = await self._repository.completed_pass_payload(job.run_id, pass_name)
        if completed is not None:
            validate_pass(pass_name, completed, source_text, entities, claims)
            if post_validate is not None:
                post_validate(completed)
            return completed
        await self._repository.renew_lease(job.id, self._settings.analysis_lease_seconds)
        try:
            response = await self._client.infer(pass_name, request)
        except ModelOutputError as error:
            await self._record_generation_failure(job, pass_name, "primary", error)
            generation_errors = [{"kind": "generation_failure", "message": str(error)}]
            await self._repository.record_pass_diagnostic(
                run_id=job.run_id,
                pass_name=pass_name,
                raw_primary_output=None,
                sanitized_primary_payload=None,
                primary_sanitization_actions=[],
                primary_validation_errors=generation_errors,
                raw_repair_output=None,
                sanitized_repair_payload=None,
                repair_sanitization_actions=[],
                repair_validation_errors=[],
                final_validation_status="generation_failure",
                final_parsed_payload=None,
            )
            raise
        payload: dict[str, Any] | None = None
        sanitized_payload: dict[str, Any] | None = None
        primary_actions: list[dict[str, Any]] = []
        try:
            payload = parse_json_object(response.raw_output)
            primary_result = sanitize_pass_payload_with_actions(
                pass_name, payload, source_text, entities
            )
            sanitized_payload = primary_result.payload
            primary_actions = list(primary_result.actions)
            validate_pass(pass_name, sanitized_payload, source_text, entities, claims)
            if post_validate is not None:
                post_validate(sanitized_payload)
        except InferenceValidationError as error:
            errors = validation_errors(error)
            await self._record_attempt(
                job,
                pass_name,
                "primary",
                response,
                payload,
                sanitized_payload,
                "invalid",
                errors,
                primary_actions,
            )
            await self._repository.renew_lease(job.id, self._settings.analysis_lease_seconds)
            try:
                repaired = await self._client.repair(pass_name, response.raw_output, errors)
            except ModelOutputError as repair_error:
                await self._record_generation_failure(job, pass_name, "repair", repair_error)
                repair_errors = [{"kind": "generation_failure", "message": str(repair_error)}]
                await self._repository.record_pass_diagnostic(
                    run_id=job.run_id,
                    pass_name=pass_name,
                    raw_primary_output=response.raw_output,
                    sanitized_primary_payload=sanitized_payload,
                    primary_sanitization_actions=primary_actions,
                    primary_validation_errors=errors,
                    raw_repair_output=None,
                    sanitized_repair_payload=None,
                    repair_sanitization_actions=[],
                    repair_validation_errors=repair_errors,
                    final_validation_status="generation_failure",
                    final_parsed_payload=None,
                )
                raise
            repaired_payload: dict[str, Any] | None = None
            sanitized_repaired_payload: dict[str, Any] | None = None
            repair_actions: list[dict[str, Any]] = []
            try:
                repaired_payload = parse_json_object(repaired.raw_output)
                repair_result = sanitize_pass_payload_with_actions(
                    pass_name, repaired_payload, source_text, entities
                )
                sanitized_repaired_payload = repair_result.payload
                repair_actions = list(repair_result.actions)
                validate_pass(pass_name, sanitized_repaired_payload, source_text, entities, claims)
                if post_validate is not None:
                    post_validate(sanitized_repaired_payload)
            except InferenceValidationError as repair_validation:
                repair_errors = validation_errors(repair_validation)
                await self._record_attempt(
                    job,
                    pass_name,
                    "repair",
                    repaired,
                    repaired_payload,
                    sanitized_repaired_payload,
                    "invalid",
                    repair_errors,
                    repair_actions,
                )
                await self._repository.record_pass_diagnostic(
                    run_id=job.run_id,
                    pass_name=pass_name,
                    raw_primary_output=response.raw_output,
                    sanitized_primary_payload=sanitized_payload,
                    primary_sanitization_actions=primary_actions,
                    primary_validation_errors=errors,
                    raw_repair_output=repaired.raw_output,
                    sanitized_repair_payload=sanitized_repaired_payload,
                    repair_sanitization_actions=repair_actions,
                    repair_validation_errors=repair_errors,
                    final_validation_status="invalid",
                    final_parsed_payload=None,
                )
                raise
            assert sanitized_repaired_payload is not None
            await self._record_attempt(
                job,
                pass_name,
                "repair",
                repaired,
                repaired_payload,
                sanitized_repaired_payload,
                "valid",
                [],
                repair_actions,
            )
            await self._repository.record_pass_diagnostic(
                run_id=job.run_id,
                pass_name=pass_name,
                raw_primary_output=response.raw_output,
                sanitized_primary_payload=sanitized_payload,
                primary_sanitization_actions=primary_actions,
                primary_validation_errors=errors,
                raw_repair_output=repaired.raw_output,
                sanitized_repair_payload=sanitized_repaired_payload,
                repair_sanitization_actions=repair_actions,
                repair_validation_errors=[],
                final_validation_status="valid",
                final_parsed_payload=sanitized_repaired_payload,
            )
            return sanitized_repaired_payload
        assert sanitized_payload is not None
        await self._record_attempt(
            job,
            pass_name,
            "primary",
            response,
            payload,
            sanitized_payload,
            "valid",
            [],
            primary_actions,
        )
        await self._repository.record_pass_diagnostic(
            run_id=job.run_id,
            pass_name=pass_name,
            raw_primary_output=response.raw_output,
            sanitized_primary_payload=sanitized_payload,
            primary_sanitization_actions=primary_actions,
            primary_validation_errors=[],
            raw_repair_output=None,
            sanitized_repair_payload=None,
            repair_sanitization_actions=[],
            repair_validation_errors=[],
            final_validation_status="valid",
            final_parsed_payload=sanitized_payload,
        )
        return sanitized_payload

    async def _record_attempt(
        self,
        job: ClaimedAnalysisJob,
        pass_name: PassName,
        attempt_kind: str,
        response: ModelResponse,
        payload: dict[str, Any] | None,
        sanitized_payload: dict[str, Any] | None,
        status: str,
        errors: list[dict[str, str]],
        sanitization_actions: list[dict[str, Any]],
    ) -> None:
        await self._repository.record_attempt(
            job.run_id,
            pass_name,
            attempt_kind,
            PROMPT_VERSIONS[pass_name],
            SCHEMA_VERSIONS[pass_name],
            self._settings.analysis_model,
            response.raw_output,
            payload,
            sanitized_payload,
            status,
            errors[0]["kind"] if errors else None,
            errors,
            sanitization_actions,
            response.duration_ms,
            response.finish_reason,
            response.completion_tokens,
        )

    async def _record_generation_failure(
        self,
        job: ClaimedAnalysisJob,
        pass_name: PassName,
        attempt_kind: str,
        error: Exception,
    ) -> None:
        await self._repository.record_attempt(
            job.run_id,
            pass_name,
            attempt_kind,
            PROMPT_VERSIONS[pass_name],
            SCHEMA_VERSIONS[pass_name],
            self._settings.analysis_model,
            None,
            None,
            None,
            "failed",
            "generation_failure",
            [{"kind": "generation_failure", "message": str(error)}],
            [],
            None,
        )

    async def _handle_execution_error(self, job: ClaimedAnalysisJob, error: Exception) -> None:
        error_kind, retryable = _classify_error(error)
        fields = self._job_log_fields(job) | {"error_kind": error_kind}
        if retryable:
            retry = await self._repository.retry_or_fail(
                job, error_kind, str(error), self._settings.analysis_max_attempts
            )
            self._logger.warning(
                "analysis job retry scheduled" if retry else "analysis job failed", extra=fields
            )
            return
        await self._repository.fail(job, error_kind, str(error))
        self._logger.warning("analysis job failed", extra=fields)

    @staticmethod
    def _job_log_fields(job: ClaimedAnalysisJob) -> dict[str, int | str]:
        return {
            "analysis_job_id": job.id,
            "analysis_run_id": job.run_id,
            "post_revision_id": job.post_revision_id,
            "priority": job.priority,
            "attempt": job.attempts,
        }


def _classify_error(error: Exception) -> tuple[str, bool]:
    """Classify provider and contract failures without collapsing diagnostics."""
    if isinstance(error, InferenceValidationError):
        kind = error.issues[0].kind if error.issues else "reference_failure"
        return kind, False
    if isinstance(error, ModelOutputError):
        return "generation_failure", False
    if isinstance(
        error, (BadRequestError, AuthenticationError, PermissionDeniedError, NotFoundError)
    ):
        return "provider_request_rejected", False
    if isinstance(
        error, (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)
    ):
        return "provider_transient", True
    if isinstance(error, APIStatusError):
        return (
            ("provider_transient", True) if error.status_code >= 500 else ("provider_error", False)
        )
    if isinstance(error, JobLeaseLostError):
        return "lease_lost", False
    return "unexpected_execution_error", False


async def run(
    stop_event: asyncio.Event | None = None,
    pool_factory: Callable[..., Awaitable[asyncpg.Pool]] = asyncpg.create_pool,
) -> None:
    """Run the worker until stopped, polling only when no job is available."""
    stop = stop_event or asyncio.Event()
    if stop.is_set():
        return
    settings = AiWorkerSettings()
    if not settings.litellm_api_key:
        raise RuntimeError("LITELLM_API_KEY must be configured for inference v3")
    logger = setup_logging(settings.service_name)
    pool = await pool_factory(settings.postgres_dsn, min_size=1, max_size=1)
    client = LiteLlmInferenceClient(
        settings.litellm_base_url,
        settings.litellm_api_key,
        settings.analysis_model,
        settings.analysis_request_timeout_seconds,
        settings.analysis_max_output_tokens,
    )
    worker = AnalysisWorker(AnalysisJobRepository(pool), client, settings, logger)
    logger.info("analysis worker started", extra={"pipeline_version": "inference_v3_5_2"})
    try:
        while not stop.is_set():
            if await worker.process_next():
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.analysis_poll_interval_seconds)
            except TimeoutError:
                continue
    finally:
        await client.close()
        await pool.close()


def main() -> None:
    """Run the worker process."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
