"""Validate golden_v0 JSONL annotations and their cross-record invariants."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

DATASET_DIRECTORY = Path(__file__).resolve().parents[1]
SCHEMA_PATH = DATASET_DIRECTORY / "annotation_schema_v1.json"
DEFAULT_ANNOTATIONS_PATH = DATASET_DIRECTORY / "data" / "annotations.jsonl"


def load_schema() -> dict[str, Any]:
    """Load the versioned annotation schema.

    Returns:
        Parsed JSON Schema for golden_v0 annotation records.
    """
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise TypeError("Annotation schema must be a JSON object")
    return schema


def validate_dataset(path: Path) -> list[str]:
    """Validate an annotation JSONL file against its structural contract.

    Args:
        path: JSONL file containing golden_v0 annotation records.

    Returns:
        Human-readable schema and semantic validation errors.
    """
    validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    errors: list[str] = []
    for line_number, record in _read_records(path, errors):
        for error in validator.iter_errors(record):
            location = ".".join(str(part) for part in error.absolute_path) or "record"
            errors.append(f"line {line_number}: {location}: {error.message}")
        if isinstance(record, dict):
            errors.extend(_semantic_errors(record, line_number))
    return errors


def _read_records(path: Path, errors: list[str]) -> Iterable[tuple[int, Any]]:
    """Yield parsed JSONL records while collecting malformed-line errors.

    Args:
        path: JSONL file to parse.
        errors: Mutable error collection for malformed input lines.

    Yields:
        Line number and parsed JSON value for each non-empty valid line.
    """
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            yield line_number, json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"line {line_number}: invalid JSON: {error.msg}")


def _semantic_errors(record: dict[str, Any], line_number: int) -> list[str]:
    """Check record invariants that JSON Schema cannot express.

    Args:
        record: Parsed annotation record.
        line_number: One-based source line containing the record.

    Returns:
        Semantic errors for spans, references, and entity resolution.
    """
    annotations = record.get("annotations")
    source = record.get("source")
    if not isinstance(annotations, dict) or not isinstance(source, dict):
        return []
    text = source.get("text")
    if not isinstance(text, str):
        return []

    errors: list[str] = []
    entities = annotations.get("entities", [])
    claims = annotations.get("claims", [])
    entity_ids = _unique_ids(entities, "entity", line_number, errors)
    claim_ids = _unique_ids(claims, "claim", line_number, errors)

    for entity in _as_dicts(entities):
        span = entity.get("mention_span")
        _check_span(span, text, line_number, "entity mention", errors)
        if isinstance(span, dict) and isinstance(entity.get("surface_form"), str):
            start, end = span.get("start"), span.get("end")
            if (
                isinstance(start, int)
                and isinstance(end, int)
                and text[start:end] != entity["surface_form"]
            ):
                errors.append(
                    f"line {line_number}: entity surface_form does not match mention_span"
                )
        _check_resolution(entity, line_number, errors)

    for stance in _as_dicts(annotations.get("stances", [])):
        _check_reference(stance.get("entity_id"), entity_ids, "stance entity", line_number, errors)
        _check_perspective(stance.get("perspective"), entity_ids, line_number, errors)
        _check_spans(stance.get("evidence_spans"), text, line_number, "stance evidence", errors)

    for claim in _as_dicts(claims):
        for entity_id in claim.get("entity_ids", []):
            _check_reference(entity_id, entity_ids, "claim entity", line_number, errors)
        _check_perspective(claim.get("attribution"), entity_ids, line_number, errors)
        _check_spans(claim.get("evidence_spans"), text, line_number, "claim evidence", errors)

    for feature in _as_dicts(annotations.get("rhetorical_features", [])):
        _check_span(feature.get("evidence_span"), text, line_number, "feature evidence", errors)
        _check_reference(
            feature.get("target_entity_id"),
            entity_ids,
            "feature target entity",
            line_number,
            errors,
        )
        _check_reference(
            feature.get("target_claim_id"), claim_ids, "feature target claim", line_number, errors
        )
        _check_perspective(feature.get("perspective"), entity_ids, line_number, errors)

    return errors


def _as_dicts(value: Any) -> list[dict[str, Any]]:
    """Filter a JSON value to its dictionary array members.

    Args:
        value: JSON value expected to contain an array of objects.

    Returns:
        Dictionary members when value is an array, otherwise an empty list.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _unique_ids(records: Any, label: str, line_number: int, errors: list[str]) -> set[str]:
    """Collect record IDs and report duplicates.

    Args:
        records: JSON value expected to contain records with IDs.
        label: Human-readable record category for error messages.
        line_number: One-based source line containing the records.
        errors: Mutable semantic-error collection.

    Returns:
        Unique string identifiers discovered in the records.
    """
    ids: set[str] = set()
    for record in _as_dicts(records):
        identifier = record.get("id")
        if isinstance(identifier, str):
            if identifier in ids:
                errors.append(f"line {line_number}: duplicate {label} id {identifier}")
            ids.add(identifier)
    return ids


def _check_spans(value: Any, text: str, line_number: int, label: str, errors: list[str]) -> None:
    """Validate every span in an expected span list.

    Args:
        value: JSON value expected to contain span objects.
        text: Source text that bounds valid spans.
        line_number: One-based source line for error messages.
        label: Human-readable span category for error messages.
        errors: Mutable semantic-error collection.
    """
    if isinstance(value, list):
        for span in value:
            _check_span(span, text, line_number, label, errors)


def _check_span(value: Any, text: str, line_number: int, label: str, errors: list[str]) -> None:
    """Validate a half-open Unicode span against source text.

    Args:
        value: JSON value expected to be a span object.
        text: Source text that bounds valid spans.
        line_number: One-based source line for error messages.
        label: Human-readable span category for error messages.
        errors: Mutable semantic-error collection.
    """
    if not isinstance(value, dict):
        return
    start, end = value.get("start"), value.get("end")
    if not isinstance(start, int) or not isinstance(end, int):
        return
    if start >= end or start < 0 or end > len(text):
        errors.append(f"line {line_number}: {label} span [{start}, {end}) is outside source text")


def _check_reference(
    identifier: Any, known_ids: set[str], label: str, line_number: int, errors: list[str]
) -> None:
    """Report a present reference that does not resolve in its record.

    Args:
        identifier: Referenced identifier, if supplied by the annotation.
        known_ids: Valid identifiers in the current annotation record.
        label: Human-readable reference category for error messages.
        line_number: One-based source line for error messages.
        errors: Mutable semantic-error collection.
    """
    if identifier is not None and (not isinstance(identifier, str) or identifier not in known_ids):
        errors.append(f"line {line_number}: {label} does not reference a known id")


def _check_perspective(
    value: Any, entity_ids: set[str], line_number: int, errors: list[str]
) -> None:
    """Ensure named-entity perspectives identify an annotated entity.

    Args:
        value: JSON value expected to be a perspective object.
        entity_ids: Valid entity IDs in the current annotation record.
        line_number: One-based source line for error messages.
        errors: Mutable semantic-error collection.
    """
    if not isinstance(value, dict):
        return
    source_kind = value.get("source_kind")
    source_entity_id = value.get("source_entity_id")
    if source_kind == "named_entity":
        _check_reference(
            source_entity_id, entity_ids, "perspective source entity", line_number, errors
        )
    elif source_entity_id is not None:
        errors.append(
            f"line {line_number}: only named_entity perspectives may set source_entity_id"
        )


def _check_resolution(entity: dict[str, Any], line_number: int, errors: list[str]) -> None:
    """Ensure unresolved mentions do not masquerade as resolved registry entities.

    Args:
        entity: Entity annotation to validate.
        line_number: One-based source line for error messages.
        errors: Mutable semantic-error collection.
    """
    registry_entity_id = entity.get("registry_entity_id")
    canonical_name = entity.get("canonical_name")
    resolution_source = entity.get("resolution_source")
    if resolution_source == "unresolved" and (
        registry_entity_id is not None or canonical_name is not None
    ):
        errors.append(
            f"line {line_number}: unresolved entity must not set canonical registry fields"
        )
    if resolution_source != "unresolved" and (
        not isinstance(registry_entity_id, str) or not isinstance(canonical_name, str)
    ):
        errors.append(f"line {line_number}: resolved entity must set canonical registry fields")


def main() -> int:
    """Run the dataset validator as a command-line program.

    Returns:
        Zero for a valid dataset, otherwise one.
    """
    parser = argparse.ArgumentParser(description="Validate golden_v0 annotations")
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_ANNOTATIONS_PATH)
    args = parser.parse_args()
    errors = validate_dataset(args.path)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"Validated {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
