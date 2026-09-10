"""Types owned by the post-analysis execution boundary."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimedAnalysisJob:
    """A leased analysis job and its immutable source text."""

    id: int
    post_revision_id: int
    post_text: str
    priority: str
    attempts: int


class ModelOutputError(ValueError):
    """Raised when a provider response cannot be parsed as the requested JSON object."""


class JobLeaseLostError(RuntimeError):
    """Raised when a job lease expires before its result can be persisted."""
