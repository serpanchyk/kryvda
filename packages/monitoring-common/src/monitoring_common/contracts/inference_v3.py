"""Shared contracts and deterministic validation for inference v3."""

import json
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any, Literal, cast

from jsonschema import Draft202012Validator

PassName = Literal["entities", "claims", "classification"]
FailureKind = Literal[
    "generation_failure",
    "json_parse_failure",
    "schema_failure",
    "grounding_failure",
    "reference_failure",
]

SCHEMA_VERSIONS: dict[PassName, str] = {
    "entities": "inference_v3_entities_v1",
    "claims": "inference_v3_claims_v1",
    "classification": "inference_v3_classification_v1",
}


@dataclass(frozen=True)
class ValidationIssue:
    """One categorized model-contract violation."""

    kind: FailureKind
    message: str


class InferenceValidationError(ValueError):
    """Raised with all deterministic violations found in one pass output."""

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(issue.message for issue in issues))


def normalize_match_text(value: str) -> str:
    """Normalize registry matching text without performing fuzzy inference."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def alias_occurs(source_text: str, alias: str) -> bool:
    """Match a literal alias case-insensitively at Unicode word boundaries."""
    normalized_source = unicodedata.normalize("NFKC", source_text).casefold()
    normalized_alias = unicodedata.normalize("NFKC", alias).casefold()
    if not normalized_alias:
        return False
    left = r"(?<!\w)" if normalized_alias[0].isalnum() else ""
    right = r"(?!\w)" if normalized_alias[-1].isalnum() else ""
    return re.search(f"{left}{re.escape(normalized_alias)}{right}", normalized_source) is not None


@lru_cache
def load_inference_schema(pass_name: PassName) -> dict[str, Any]:
    """Load one packaged inference-v3 JSON Schema."""
    path = files("monitoring_common.contracts").joinpath(
        f"schemas/{SCHEMA_VERSIONS[pass_name]}.json"
    )
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def parse_json_object(raw_output: str) -> dict[str, Any]:
    """Decode exactly one JSON object with a categorized parse error."""
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as error:
        raise InferenceValidationError(
            [ValidationIssue("json_parse_failure", f"invalid JSON: {error.msg}")]
        ) from error
    if not isinstance(payload, dict):
        raise InferenceValidationError(
            [ValidationIssue("schema_failure", "model response JSON must be an object")]
        )
    return cast(dict[str, Any], payload)


def validate_pass(
    pass_name: PassName,
    payload: Mapping[str, Any],
    source_text: str,
    entities: Sequence[Mapping[str, Any]] = (),
    claims: Sequence[Mapping[str, Any]] = (),
) -> None:
    """Validate schema, exact text, local references, and pair completeness."""
    validator = Draft202012Validator(load_inference_schema(pass_name))
    schema_errors = sorted(validator.iter_errors(payload), key=lambda error: str(error.path))
    if schema_errors:
        raise InferenceValidationError(
            [ValidationIssue("schema_failure", error.message) for error in schema_errors]
        )
    if pass_name == "entities":
        _validate_entities(payload, source_text)
    elif pass_name == "claims":
        _validate_claims(payload, source_text, entities)
    else:
        _validate_classifications(payload, entities, claims)


def _validate_entities(payload: Mapping[str, Any], source_text: str) -> None:
    issues: list[ValidationIssue] = []
    all_mentions: list[str] = []
    for entity in cast(list[Mapping[str, Any]], payload["entities"]):
        mentions = cast(list[str], entity["mentions"])
        all_mentions.extend(mentions)
        for mention in mentions:
            if mention not in source_text:
                issues.append(
                    ValidationIssue(
                        "grounding_failure", f"entity mention is not exact source text: {mention!r}"
                    )
                )
    duplicates = [mention for mention, count in Counter(all_mentions).items() if count > 1]
    if duplicates:
        issues.append(
            ValidationIssue(
                "reference_failure", f"mentions occur in multiple entity groups: {duplicates!r}"
            )
        )
    if issues:
        raise InferenceValidationError(issues)


def _validate_claims(
    payload: Mapping[str, Any], source_text: str, entities: Sequence[Mapping[str, Any]]
) -> None:
    issues: list[ValidationIssue] = []
    entity_by_id = {cast(str, entity["id"]): entity for entity in entities}
    monitored_ids = {
        entity_id for entity_id, entity in entity_by_id.items() if bool(entity["monitored"])
    }
    for claim in cast(list[Mapping[str, Any]], payload["claims"]):
        evidence = cast(str, claim["evidence_text"])
        if evidence not in source_text:
            issues.append(
                ValidationIssue(
                    "grounding_failure", f"claim evidence is not exact source text: {evidence!r}"
                )
            )
        ids = cast(list[str], claim["entity_ids"])
        if len(ids) != len(set(ids)):
            issues.append(
                ValidationIssue("reference_failure", "claim entity references must be unique")
            )
        unknown = sorted(set(ids) - entity_by_id.keys())
        if unknown:
            issues.append(
                ValidationIssue("reference_failure", f"unknown claim entity references: {unknown}")
            )
        if not monitored_ids.intersection(ids):
            issues.append(
                ValidationIssue("reference_failure", "every claim must involve a monitored entity")
            )
        attribution = cast(Mapping[str, Any], claim["attribution"])
        source_kind = attribution["source_kind"]
        source_id = attribution["source_entity_id"]
        if source_kind == "named_entity" and source_id not in entity_by_id:
            issues.append(
                ValidationIssue(
                    "reference_failure", f"unknown named attribution reference: {source_id!r}"
                )
            )
        if source_kind != "named_entity" and source_id is not None:
            issues.append(
                ValidationIssue(
                    "reference_failure", "only named_entity attribution may carry an entity ID"
                )
            )
    if issues:
        raise InferenceValidationError(issues)


def _validate_classifications(
    payload: Mapping[str, Any],
    entities: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
) -> None:
    monitored = {cast(str, entity["id"]) for entity in entities if bool(entity["monitored"])}
    expected = {
        (cast(str, claim["id"]), entity_id)
        for claim in claims
        for entity_id in cast(list[str], claim["entity_ids"])
        if entity_id in monitored
    }
    actual_rows = cast(list[Mapping[str, Any]], payload["classifications"])
    actual = {(cast(str, row["claim_id"]), cast(str, row["entity_id"])) for row in actual_rows}
    issues: list[ValidationIssue] = []
    if len(actual) != len(actual_rows):
        issues.append(ValidationIssue("reference_failure", "classification pairs must be unique"))
    if actual != expected:
        issues.append(
            ValidationIssue(
                "reference_failure",
                f"classification pairs differ: missing={sorted(expected - actual)}, "
                f"extra={sorted(actual - expected)}",
            )
        )
    for row in actual_rows:
        rhetoric = cast(list[str], row["rhetoric"])
        if len(rhetoric) != len(set(rhetoric)):
            issues.append(ValidationIssue("schema_failure", "rhetoric labels must be unique"))
        if row["stance"] != "негативне" and row["rhetoric"]:
            issues.append(
                ValidationIssue(
                    "schema_failure", "rhetoric must be empty unless stance is негативне"
                )
            )
    if issues:
        raise InferenceValidationError(issues)


def validation_errors(error: InferenceValidationError) -> list[dict[str, str]]:
    """Serialize categorized validation issues for repair prompts and persistence."""
    return [{"kind": issue.kind, "message": issue.message} for issue in error.issues]
