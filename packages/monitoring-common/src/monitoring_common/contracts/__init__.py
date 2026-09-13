"""Cross-service contracts shared across Telegram Monitor boundaries."""

from monitoring_common.contracts.inference_v3 import (
    SCHEMA_VERSIONS,
    InferenceValidationError,
    PassName,
    SanitizedPayload,
    ValidationIssue,
    alias_occurs,
    load_inference_schema,
    matched_registry_entity_ids,
    normalize_match_text,
    parse_json_object,
    resolve_registry_mention,
    sanitize_pass_payload,
    sanitize_pass_payload_with_actions,
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
    "SanitizedPayload",
    "SCHEMA_VERSIONS",
    "ValidationIssue",
    "alias_occurs",
    "load_inference_schema",
    "matched_registry_entity_ids",
    "normalize_match_text",
    "parse_json_object",
    "sanitize_pass_payload",
    "sanitize_pass_payload_with_actions",
    "resolve_registry_mention",
    "validate_pass",
    "validation_errors",
]
