"""Leased PostgreSQL worker for candidate post-analysis extraction."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import asyncpg
from monitoring_common.config import BaseServiceSettings
from monitoring_common.contracts import ExtractionValidationError, validate_extraction
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

from telegram_monitor_ai_worker.client import LiteLlmExtractionClient
from telegram_monitor_ai_worker.models import (
    ClaimedAnalysisJob,
    JobLeaseLostError,
    ModelOutputError,
)
from telegram_monitor_ai_worker.prompt import PROMPT_VERSION
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
    analysis_max_attempts: int = 3


class ExtractionClient(Protocol):
    """Model boundary used by worker orchestration."""

    async def extract(self, post_text: str) -> dict[str, Any]:
        """Return a decoded extraction payload."""


class AnalysisWorker:
    """Lease, execute, validate, and finalize one analysis job at a time."""

    def __init__(
        self,
        repository: AnalysisJobRepository,
        client: ExtractionClient,
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
            self._settings.analysis_lease_seconds, self._settings.analysis_max_attempts
        )
        if job is None:
            return False
        self._logger.info("analysis job leased", extra=self._job_log_fields(job))
        try:
            payload = await self._client.extract(job.post_text)
            validate_extraction(payload, job.post_text)
        except Exception as error:
            await self._handle_execution_error(job, error)
            return True
        try:
            await self._repository.complete(
                job, payload, PROMPT_VERSION, self._settings.analysis_model
            )
        except JobLeaseLostError:
            self._logger.warning("analysis job lease lost", extra=self._job_log_fields(job))
            return True
        self._logger.info("analysis job completed", extra=self._job_log_fields(job))
        return True

    async def _handle_execution_error(self, job: ClaimedAnalysisJob, error: Exception) -> None:
        error_kind, retryable = _classify_error(error)
        fields = self._job_log_fields(job) | {"error_kind": error_kind}
        if retryable:
            retry = await self._repository.retry_or_fail(
                job, error_kind, str(error), self._settings.analysis_max_attempts
            )
            message = "analysis job retry scheduled" if retry else "analysis job failed"
            self._logger.warning(message, extra=fields)
            return
        await self._repository.fail(job, error_kind, str(error))
        self._logger.warning("analysis job failed", extra=fields)

    @staticmethod
    def _job_log_fields(job: ClaimedAnalysisJob) -> dict[str, int | str]:
        return {
            "analysis_job_id": job.id,
            "post_revision_id": job.post_revision_id,
            "priority": job.priority,
            "attempt": job.attempts,
        }


def _classify_error(error: Exception) -> tuple[str, bool]:
    """Classify provider and validation errors without persisting provider payloads."""
    if isinstance(error, (ModelOutputError, ExtractionValidationError)):
        return "invalid_model_output", False
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
        raise RuntimeError("LITELLM_API_KEY must be configured for post analysis")
    logger = setup_logging(settings.service_name)
    pool = await pool_factory(settings.postgres_dsn, min_size=1, max_size=1)
    client = LiteLlmExtractionClient(
        settings.litellm_base_url,
        settings.litellm_api_key,
        settings.analysis_model,
        settings.analysis_request_timeout_seconds,
    )
    worker = AnalysisWorker(AnalysisJobRepository(pool), client, settings, logger)
    logger.info("analysis worker started")
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
