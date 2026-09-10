"""Cross-service contracts shared across Telegram Monitor boundaries."""

from monitoring_common.contracts.post_analysis_extraction import (
    EXTRACTION_SCHEMA_VERSION,
    ExtractionValidationError,
    load_extraction_schema,
    validate_extraction,
)

__all__ = [
    "EXTRACTION_SCHEMA_VERSION",
    "ExtractionValidationError",
    "load_extraction_schema",
    "validate_extraction",
]
