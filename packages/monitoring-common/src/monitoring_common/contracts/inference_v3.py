"""Shared contracts and deterministic validation for inference v3."""

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from copy import deepcopy
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
    "claims": "inference_v3_claims_v4",
    "classification": "inference_v3_classification_v1",
}


@dataclass(frozen=True)
class ValidationIssue:
    """One categorized model-contract violation."""

    kind: FailureKind
    message: str


@dataclass(frozen=True)
class SanitizedPayload:
    """A cleaned payload and the deterministic actions that produced it."""

    payload: dict[str, Any]
    actions: tuple[dict[str, Any], ...]


class InferenceValidationError(ValueError):
    """Raised with all deterministic violations found in one pass output."""

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(issue.message for issue in issues))


def normalize_match_text(value: str) -> str:
    """Normalize registry matching text without performing fuzzy inference."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def alias_occurs(source_text: str, alias: str) -> bool:
    """Match an alias exactly or through Ukrainian/Russian word inflection."""
    normalized_source = unicodedata.normalize("NFKC", source_text).casefold()
    normalized_alias = unicodedata.normalize("NFKC", alias).casefold()
    if not normalized_alias:
        return False
    left = r"(?<!\w)" if normalized_alias[0].isalnum() else ""
    right = r"(?!\w)" if normalized_alias[-1].isalnum() else ""
    if re.search(f"{left}{re.escape(normalized_alias)}{right}", normalized_source) is not None:
        return True
    alias_tokens = _word_tokens(alias)
    source_tokens = _word_tokens(source_text)
    if not alias_tokens or len(alias_tokens) > len(source_tokens):
        return False
    for start in range(len(source_tokens) - len(alias_tokens) + 1):
        source_window = source_tokens[start : start + len(alias_tokens)]
        if all(
            _tokens_match(expected, actual) for expected, actual in zip(alias_tokens, source_window)
        ):
            return True
    return False


def matched_registry_entity_ids(
    source_text: str, aliases: Sequence[Mapping[str, Any]], monitored_only: bool = True
) -> list[int]:
    """Return entities admitted by direct aliases or unique person-surname forms.

    A surname inferred from a multi-token person alias is safe only when it maps to one eligible
    registry entity. This admits inflected surname-only Telegram mentions without guessing among
    people who share a surname.
    """
    eligible = [row for row in aliases if not monitored_only or bool(row.get("monitored"))]
    matched = {
        int(row["entity_id"])
        for row in eligible
        if alias_occurs(source_text, cast(str, row["alias"]))
    }
    surname_owners: dict[str, set[int]] = {}
    for row in eligible:
        if row.get("coarse_type") != "person":
            continue
        tokens = _word_tokens(cast(str, row["alias"]))
        if len(tokens) < 2 or len(tokens[-1]) < 4:
            continue
        surname_owners.setdefault(tokens[-1], set()).add(int(row["entity_id"]))
    for surname, owners in surname_owners.items():
        if len(owners) == 1 and alias_occurs(source_text, surname):
            matched.update(owners)
    return sorted(matched)


def matched_registry_entities(
    source_text: str, aliases: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Return each admitted monitored registry entity with exact source surface forms."""
    matched_ids = matched_registry_entity_ids(source_text, aliases)
    matches: list[dict[str, Any]] = []
    for entity_id in matched_ids:
        rows = [row for row in aliases if int(row["entity_id"]) == entity_id]
        surfaces: list[tuple[int, str]] = []
        for row in rows:
            surfaces.extend(_alias_surfaces(source_text, cast(str, row["alias"])))
        if not surfaces:
            surname_rows = [
                row
                for row in rows
                if row.get("coarse_type") == "person"
                and len(_word_tokens(cast(str, row["alias"]))) >= 2
            ]
            for row in surname_rows:
                surname = _word_tokens(cast(str, row["alias"]))[-1]
                surfaces.extend(_alias_surfaces(source_text, surname))
        mentions: list[str] = []
        for _, surface in sorted(set(surfaces)):
            if surface not in mentions:
                mentions.append(surface)
        if not mentions:
            raise ValueError(f"prefilter match {entity_id} has no exact source surface")
        first = rows[0]
        matches.append(
            {
                "entity_id": entity_id,
                "canonical_name": first["canonical_name"],
                "monitored": True,
                "mentions": mentions,
            }
        )
    return matches


def _alias_surfaces(source_text: str, alias: str) -> list[tuple[int, str]]:
    """Find every exact source substring accepted by the alias matcher."""
    alias_tokens = _word_tokens(alias)
    source_tokens = list(
        re.finditer(r"[^\W\d_]+(?:[’'ʼ-][^\W\d_]+)*|\d+", source_text, re.IGNORECASE)
    )
    if not alias_tokens or len(alias_tokens) > len(source_tokens):
        return []
    results: list[tuple[int, str]] = []
    for start in range(len(source_tokens) - len(alias_tokens) + 1):
        window = source_tokens[start : start + len(alias_tokens)]
        if all(
            _tokens_match(expected, match.group(0).casefold())
            for expected, match in zip(alias_tokens, window)
        ):
            results.append((window[0].start(), source_text[window[0].start() : window[-1].end()]))
    return results


def resolve_registry_mention(
    mention: str, aliases: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    """Return the unique registry row for one mention, or ``None`` when ambiguous/unresolved."""
    normalized = normalize_match_text(mention)
    exact = [row for row in aliases if cast(str, row["normalized_alias"]) == normalized]
    matches = exact or [row for row in aliases if alias_occurs(mention, cast(str, row["alias"]))]
    entity_ids = {int(row["entity_id"]) for row in matches}
    if not entity_ids:
        surname_matches = []
        for row in aliases:
            tokens = _word_tokens(cast(str, row["alias"]))
            if (
                row.get("coarse_type") == "person"
                and len(tokens) >= 2
                and len(tokens[-1]) >= 4
                and alias_occurs(mention, tokens[-1])
            ):
                surname_matches.append(row)
        entity_ids = {int(row["entity_id"]) for row in surname_matches}
        matches = surname_matches
    if len(entity_ids) != 1:
        return None
    return next(row for row in matches if int(row["entity_id"]) in entity_ids)


@lru_cache(maxsize=4096)
def _inflection_forms(token: str) -> frozenset[str]:
    """Generate conservative Ukrainian/Russian nominal case forms."""
    normalized = unicodedata.normalize("NFKC", token).casefold()
    if len(normalized) <= 3 or not re.search(r"[а-яіїєґёэъы]", normalized):
        return frozenset({normalized})
    forms = {normalized}
    if normalized.endswith(("ій", "ий", "ый")):
        stem = normalized[:-2]
        forms.update(stem + suffix for suffix in ("ого", "ому", "им", "ым", "ім"))
        if normalized.endswith("ій"):
            forms.update(stem + suffix for suffix in ("ія", "ію", "ієм", "ієві"))
    elif normalized.endswith("а"):
        stem = normalized[:-1]
        forms.update(stem + suffix for suffix in ("и", "і", "у", "ою", "е", "о"))
    elif normalized.endswith("я"):
        stem = normalized[:-1]
        forms.update(stem + suffix for suffix in ("і", "ї", "и", "ю", "єю", "ею", "ей"))
    elif normalized.endswith("о"):
        stem = normalized[:-1]
        forms.update(stem + suffix for suffix in ("а", "у", "ом", "і", "е"))
    elif normalized.endswith("ь"):
        stem = normalized[:-1]
        forms.update(stem + suffix for suffix in ("я", "ю", "ем", "єм", "і", "е"))
    elif re.search(r"[бвгґджзклмнпрстфхцчшщ]$", normalized):
        forms.update(normalized + suffix for suffix in ("а", "у", "ом", "ем", "і", "ові", "еві"))
    return frozenset(forms)


@lru_cache(maxsize=2048)
def _word_tokens(value: str) -> tuple[str, ...]:
    """Tokenize words while retaining apostrophe and hyphen compounds."""
    return tuple(
        match.group(0)
        for match in re.finditer(r"[^\W\d_]+(?:[’'ʼ-][^\W\d_]+)*|\d+", value.casefold())
    )


def _tokens_match(alias_token: str, source_token: str) -> bool:
    return source_token in _inflection_forms(alias_token)


def sanitize_pass_payload(
    pass_name: PassName, payload: Mapping[str, Any], source_text: str
) -> dict[str, Any]:
    """Apply deterministic, semantics-preserving cleanup before pass validation."""
    return sanitize_pass_payload_with_actions(pass_name, payload, source_text, ()).payload


def sanitize_pass_payload_with_actions(
    pass_name: PassName,
    payload: Mapping[str, Any],
    source_text: str,
    entities: Sequence[Mapping[str, Any]],
) -> SanitizedPayload:
    """Clean one pass payload and retain item-level recovery diagnostics."""
    sanitized = deepcopy(dict(payload))
    actions: list[dict[str, Any]] = []
    if pass_name == "claims" and isinstance(sanitized.get("claims"), list):
        sanitized["claims"] = _sanitize_claims(
            cast(list[Any], sanitized["claims"]), source_text, entities, actions
        )
        return SanitizedPayload(sanitized, tuple(actions))
    if pass_name != "entities" or not isinstance(sanitized.get("entities"), list):
        return SanitizedPayload(sanitized, tuple(actions))
    groups: list[Any] = []
    for candidate in sanitized["entities"]:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("mentions"), list):
            groups.append(candidate)
            continue
        mentions: list[Any] = []
        seen: set[str] = set()
        for mention in candidate["mentions"]:
            if not isinstance(mention, str):
                mentions.append(mention)
            elif mention in source_text and mention not in seen:
                seen.add(mention)
                mentions.append(mention)
            elif mention in seen:
                actions.append({"action": "deduplicated_mention", "mention": mention})
            else:
                actions.append({"action": "dropped_ungrounded_mention", "mention": mention})
        if mentions:
            candidate["mentions"] = mentions
            groups.append(candidate)
        else:
            actions.append({"action": "dropped_empty_entity_group"})
    sanitized["entities"] = groups
    return SanitizedPayload(sanitized, tuple(actions))


def _sanitize_claims(
    claims: list[Any],
    source_text: str,
    entities: Sequence[Mapping[str, Any]],
    actions: list[dict[str, Any]],
) -> list[Any]:
    entity_by_id = {cast(str, entity["id"]): entity for entity in entities}
    monitored_ids = {
        entity_id for entity_id, entity in entity_by_id.items() if bool(entity["monitored"])
    }
    retained: list[Any] = []
    fingerprints: set[str] = set()
    for index, raw_claim in enumerate(claims):
        if not isinstance(raw_claim, dict):
            actions.append({"action": "dropped_claim", "index": index, "reason": "not_object"})
            continue
        claim = cast(dict[str, Any], raw_claim)
        if "presentation" in claim:
            claim.pop("presentation")
            actions.append({"action": "removed_obsolete_presentation", "index": index})
        allowed = {
            "normalized_text",
            "entity_ids",
            "evidence_text",
            "attribution",
            "epistemic_status",
        }
        unknown_fields = set(claim) - allowed
        if unknown_fields:
            for field in unknown_fields:
                claim.pop(field)
            actions.append({"action": "removed_unknown_claim_fields", "index": index})
        required = {
            "normalized_text",
            "entity_ids",
            "evidence_text",
            "attribution",
            "epistemic_status",
        }
        if not required.issubset(claim):
            actions.append({"action": "dropped_claim", "index": index, "reason": "missing_fields"})
            continue
        if not isinstance(claim["normalized_text"], str) or not claim["normalized_text"]:
            actions.append(
                {"action": "dropped_claim", "index": index, "reason": "invalid_normalized_text"}
            )
            continue
        if claim["epistemic_status"] not in {"ствердження", "невпевнене", "питання"}:
            actions.append(
                {"action": "dropped_claim", "index": index, "reason": "invalid_epistemic_status"}
            )
            continue
        if not isinstance(claim["entity_ids"], list):
            actions.append(
                {"action": "dropped_claim", "index": index, "reason": "invalid_entity_ids"}
            )
            continue
        ids: list[str] = []
        for entity_id in claim["entity_ids"]:
            if isinstance(entity_id, str) and entity_id in entity_by_id and entity_id not in ids:
                ids.append(entity_id)
        if ids != claim["entity_ids"]:
            actions.append({"action": "sanitized_claim_entity_ids", "index": index})
        if not monitored_ids.intersection(ids):
            actions.append(
                {"action": "dropped_claim", "index": index, "reason": "no_monitored_target"}
            )
            continue
        claim["entity_ids"] = ids
        evidence = claim["evidence_text"]
        if not isinstance(evidence, str):
            actions.append(
                {"action": "dropped_claim", "index": index, "reason": "invalid_evidence"}
            )
            continue
        aligned = _realign_evidence(evidence, source_text)
        if aligned is None:
            actions.append(
                {"action": "dropped_claim", "index": index, "reason": "ungrounded_evidence"}
            )
            continue
        if aligned != evidence:
            claim["evidence_text"] = aligned
            actions.append({"action": "realigned_evidence", "index": index})
        attribution = claim["attribution"]
        if isinstance(attribution, dict):
            unknown_attribution_fields = set(attribution) - {"source_entity_id", "source_kind"}
            if unknown_attribution_fields:
                for field in unknown_attribution_fields:
                    attribution.pop(field)
                actions.append({"action": "removed_unknown_attribution_fields", "index": index})
        sanitized_attribution = _sanitize_attribution(attribution, entity_by_id)
        if sanitized_attribution is None:
            actions.append(
                {"action": "dropped_claim", "index": index, "reason": "invalid_attribution"}
            )
            continue
        if sanitized_attribution != attribution:
            claim["attribution"] = sanitized_attribution
            attribution = sanitized_attribution
            actions.append({"action": "sanitized_attribution", "index": index})
        fingerprint = json.dumps(
            {
                "normalized_text": claim["normalized_text"],
                "entity_ids": ids,
                "evidence_text": claim["evidence_text"],
                "attribution": attribution,
                "epistemic_status": claim["epistemic_status"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if fingerprint in fingerprints:
            actions.append({"action": "deduplicated_claim", "index": index})
            continue
        fingerprints.add(fingerprint)
        retained.append(claim)
    return retained


def _valid_attribution(attribution: Any, entity_by_id: Mapping[str, Mapping[str, Any]]) -> bool:
    if not isinstance(attribution, Mapping):
        return False
    source_kind = attribution.get("source_kind")
    source_id = attribution.get("source_entity_id")
    if source_kind == "named_entity":
        return isinstance(source_id, str) and source_id in entity_by_id
    return source_kind in {"channel_editorial", "external_unnamed"} and source_id is None


def _sanitize_attribution(
    attribution: Any, entity_by_id: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any] | None:
    """Keep valid claims by replacing unsafe attribution with a conservative null source."""
    if not isinstance(attribution, Mapping):
        return None
    source_kind = attribution.get("source_kind")
    source_id = attribution.get("source_entity_id")
    if source_kind in {"channel_editorial", "external_unnamed"}:
        return {"source_kind": source_kind, "source_entity_id": None}
    if source_kind == "named_entity" and isinstance(source_id, str) and source_id in entity_by_id:
        return {"source_kind": source_kind, "source_entity_id": source_id}
    if source_kind == "named_entity":
        return {"source_kind": "external_unnamed", "source_entity_id": None}
    return None


def _realign_evidence(evidence: str, source_text: str) -> str | None:
    if evidence in source_text:
        return evidence
    normalized_evidence = _normalize_evidence_text(evidence)
    if not normalized_evidence:
        return None
    normalized_source, positions = _normalized_source_with_positions(source_text)
    starts: list[int] = []
    position = normalized_source.find(normalized_evidence)
    while position >= 0:
        starts.append(position)
        position = normalized_source.find(normalized_evidence, position + 1)
    if len(starts) != 1:
        return None
    start = starts[0]
    end = start + len(normalized_evidence)
    return source_text[positions[start][0] : positions[end - 1][1]]


def _normalize_evidence_text(value: str) -> str:
    normalized, _ = _normalized_source_with_positions(value)
    return normalized


def _normalized_source_with_positions(value: str) -> tuple[str, list[tuple[int, int]]]:
    punctuation = str.maketrans(
        {
            "‘": "'",
            "’": "'",
            "ʼ": "'",
            "`": "'",
            "“": '"',
            "”": '"',
            "„": '"',
            "«": '"',
            "»": '"',
            "–": "-",
            "—": "-",
            "―": "-",
            "‐": "-",
            "‑": "-",
            "‒": "-",
        }
    )
    output: list[str] = []
    positions: list[tuple[int, int]] = []
    whitespace = False
    whitespace_start = 0
    for index, character in enumerate(value):
        converted = unicodedata.normalize("NFKC", character).translate(punctuation)
        for item in converted:
            if item.isspace():
                if not whitespace:
                    whitespace = True
                    whitespace_start = index
                continue
            if whitespace and output:
                output.append(" ")
                positions.append((whitespace_start, index))
            whitespace = False
            output.append(item.casefold())
            positions.append((index, index + 1))
    return "".join(output), positions


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
    mention_owner: dict[str, int] = {}
    duplicate_groups: list[str] = []
    for group_index, entity in enumerate(cast(list[Mapping[str, Any]], payload["entities"])):
        mentions = cast(list[str], entity["mentions"])
        for mention in mentions:
            if mention not in source_text:
                issues.append(
                    ValidationIssue(
                        "grounding_failure", f"entity mention is not exact source text: {mention!r}"
                    )
                )
            owner = mention_owner.setdefault(mention, group_index)
            if owner != group_index and mention not in duplicate_groups:
                duplicate_groups.append(mention)
    if duplicate_groups:
        issues.append(
            ValidationIssue(
                "reference_failure",
                f"mentions occur in multiple entity groups: {duplicate_groups!r}",
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
