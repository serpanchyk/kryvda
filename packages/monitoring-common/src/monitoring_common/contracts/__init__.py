"""Cross-service contracts shared across Telegram Monitor boundaries."""

from monitoring_common.contracts.inference_v3 import (
    SCHEMA_VERSIONS,
    InferenceValidationError,
    PassName,
    ValidationIssue,
    alias_occurs,
    load_inference_schema,
    normalize_match_text,
    parse_json_object,
    validate_pass,
    validation_errors,
)
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
    "InferenceValidationError",
    "PassName",
    "SCHEMA_VERSIONS",
    "ValidationIssue",
    "alias_occurs",
    "load_inference_schema",
    "normalize_match_text",
    "parse_json_object",
    "validate_pass",
    "validation_errors",
]
