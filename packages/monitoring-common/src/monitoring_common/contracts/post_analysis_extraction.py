"""Validation for text-grounded post-analysis extraction results."""

import json
from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from typing import Any, cast

from jsonschema import Draft202012Validator

EXTRACTION_SCHEMA_VERSION = "extraction_schema_v1"


class ExtractionValidationError(ValueError):
    """Raised when an extraction response is not grounded in its source text."""


@lru_cache
def load_extraction_schema() -> dict[str, Any]:
    """Load the versioned JSON Schema packaged with the shared contracts."""
    schema_path = files("monitoring_common.contracts").joinpath(
        "schemas/post_analysis_extraction_schema_v1.json"
    )
    return cast(dict[str, Any], json.loads(schema_path.read_text(encoding="utf-8")))


@lru_cache
def _extraction_validator() -> Draft202012Validator:
    """Build the reusable structural validator for extraction responses."""
    return Draft202012Validator(load_extraction_schema())


def validate_extraction(payload: Mapping[str, Any], source_text: str) -> None:
    """Validate response structure, local references, and evidence against source text."""
    _validate_schema(payload)
    annotations = payload["annotations"]
    entities = annotations["entities"]
    entity_ids = {entity["id"] for entity in entities}
    claim_ids = {claim["id"] for claim in annotations["claims"]}

    for entity in entities:
        span = entity["mention_span"]
        _validate_span(span, source_text)
        if source_text[span["start"] : span["end"]] != entity["surface_form"]:
            raise ExtractionValidationError("entity surface_form must match its mention_span")

    for stance in annotations["stances"]:
        _validate_entity_reference(stance["entity_id"], entity_ids)
        _validate_perspective(stance["perspective"], entity_ids)
        _validate_spans(stance["evidence_spans"], source_text)

    for claim in annotations["claims"]:
        for entity_id in claim["entity_ids"]:
            _validate_entity_reference(entity_id, entity_ids)
        _validate_perspective(claim["attribution"], entity_ids)
        _validate_spans(claim["evidence_spans"], source_text)

    for feature in annotations["rhetorical_features"]:
        _validate_span(feature["evidence_span"], source_text)
        _validate_perspective(feature["perspective"], entity_ids)
        _validate_optional_reference(feature.get("target_entity_id"), entity_ids, "entity")
        _validate_optional_reference(feature.get("target_claim_id"), claim_ids, "claim")


def _validate_schema(payload: Mapping[str, Any]) -> None:
    """Raise the first deterministic JSON Schema error, if any."""
    errors = sorted(_extraction_validator().iter_errors(payload), key=lambda error: str(error.path))
    if errors:
        raise ExtractionValidationError(errors[0].message) from errors[0]


def _validate_spans(spans: list[Mapping[str, int]], source_text: str) -> None:
    """Validate every evidence span against the supplied source text."""
    for span in spans:
        _validate_span(span, source_text)


def _validate_span(span: Mapping[str, int], source_text: str) -> None:
    """Require a non-empty half-open span within the source-text boundaries."""
    start = span["start"]
    end = span["end"]
    if start >= end or end > len(source_text):
        raise ExtractionValidationError("span must be non-empty and within source_text")


def _validate_entity_reference(entity_id: str, entity_ids: set[str]) -> None:
    """Require an entity reference to resolve within the response."""
    if entity_id not in entity_ids:
        raise ExtractionValidationError(f"unknown entity reference: {entity_id}")


def _validate_optional_reference(
    reference_id: str | None,
    known_ids: set[str],
    reference_kind: str,
) -> None:
    """Require an optional local reference to resolve when it is present."""
    if reference_id is not None and reference_id not in known_ids:
        raise ExtractionValidationError(f"unknown {reference_kind} reference: {reference_id}")


def _validate_perspective(perspective: Mapping[str, str | None], entity_ids: set[str]) -> None:
    """Validate the speaker rule for an attributed perspective."""
    source_kind = perspective["source_kind"]
    source_entity_id = perspective["source_entity_id"]
    if source_kind == "named_entity":
        if source_entity_id is None:
            raise ExtractionValidationError("named_entity perspective requires source_entity_id")
        _validate_entity_reference(source_entity_id, entity_ids)
    elif source_entity_id is not None:
        raise ExtractionValidationError("only named_entity perspective may have source_entity_id")
