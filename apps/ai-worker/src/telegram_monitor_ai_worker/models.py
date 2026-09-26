"""Types owned by the inference-v3 execution boundary."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimedAnalysisJob:
    """A leased analysis job and its immutable source text."""

    id: int
    post_revision_id: int
    post_text: str
    priority: str
    attempts: int
    run_id: int
    retry_round: int = 0


@dataclass(frozen=True)
class ModelResponse:
    """Raw provider content and request duration."""

    raw_output: str
    duration_ms: int
    finish_reason: str | None = None
    completion_tokens: int | None = None


class ModelOutputError(ValueError):
    """Raised when a generation contains no usable content."""


class JobLeaseLostError(RuntimeError):
    """Raised when a job lease expires before its result can be persisted."""
