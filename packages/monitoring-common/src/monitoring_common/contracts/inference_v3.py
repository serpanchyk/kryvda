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

PassName = Literal["candidates", "entities", "claims", "targets", "classification"]
FailureKind = Literal[
    "generation_failure",
    "json_parse_failure",
    "schema_failure",
    "grounding_failure",
    "reference_failure",
]

SCHEMA_VERSIONS: dict[PassName, str] = {
    "candidates": "inference_v3_candidates_v1",
    "entities": "inference_v3_entities_v1",
    "claims": "inference_v3_claims_v4",
    "targets": "inference_v3_targets_v2",
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


_FOREIGN_STATE_SUFFIX = re.compile(
    r"[\s(«\"]*(?:рф|росії|россии|російської\s+федерації|российской\s+федерации|кнр|кндр|"
    r"китаю|китая|сша|туреччини|турции|білорусі|беларуси|ірану|ирана|польщі|польши|"
    r"угорщини|венгрии|німеччини|германии|франції|франции|великобританії|великобритании|"
    r"британії|британии|ізраїлю|израиля|грузії|грузии|молдови|молдовы|румунії|румынии|"
    r"словаччини|словакии|японії|японии|індії|индии)(?!\w)",
    re.IGNORECASE,
)
_FOREIGN_STATE_PREFIX = re.compile(
    r"(?:російськ|российск|китайськ|китайск|американськ|американск|турецьк|турецк|"
    r"білоруськ|белорусск|іранськ|иранск|польськ|польск|угорськ|венгерск|німецьк|немецк|"
    r"французьк|французск|британськ|британск|ізраїльськ|израильск|грузинськ|грузинск)"
    r"\w*\s+$",
    re.IGNORECASE,
)


def foreign_state_context(source_text: str, start: int, end: int) -> bool:
    """Tell whether a state-body alias occurrence names another country's institution.

    ``Міноборони рф``, ``МЗС КНР`` and ``російський Генштаб`` share Ukrainian registry aliases
    but never refer to the monitored Ukrainian body.
    """
    if _FOREIGN_STATE_SUFFIX.match(source_text, end) is not None:
        return True
    return _FOREIGN_STATE_PREFIX.search(source_text[max(0, start - 40) : start]) is not None


def mention_is_only_foreign_state(source_text: str, mention: str) -> bool:
    """Return True when every exact occurrence of a mention carries a foreign-state marker."""
    starts: list[int] = []
    position = source_text.find(mention)
    while position != -1:
        starts.append(position)
        position = source_text.find(mention, position + 1)
    return bool(starts) and all(
        foreign_state_context(source_text, start, start + len(mention)) for start in starts
    )


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

    A surname taken from a person's canonical name is safe only when it maps to one eligible
    registry entity. This admits inflected surname-only Telegram mentions without guessing among
    people who share a surname.
    """
    eligible = [row for row in aliases if not monitored_only or bool(row.get("monitored"))]
    matched = {
        int(row["entity_id"]) for row in eligible if _registry_alias_occurs(source_text, row)
    }
    surname_owners: dict[str, set[int]] = {}
    for row in eligible:
        surname = _registry_surname(row)
        if surname is not None:
            surname_owners.setdefault(surname, set()).add(int(row["entity_id"]))
    for surname, owners in surname_owners.items():
        if len(owners) == 1 and alias_occurs(source_text, surname):
            matched.update(owners)
    return sorted(matched)


def _registry_surname(row: Mapping[str, Any]) -> str | None:
    """Return the surname implied by a person's canonical name, if long enough to be safe.

    Only the canonical name counts: descriptive aliases (``мер Києва``) and reversed ones
    (``Корецький Сергій``) would otherwise turn a city or a first name into a "surname".
    """
    if row.get("coarse_type") != "person":
        return None
    tokens = _word_tokens(cast(str, row.get("canonical_name") or row["alias"]))
    if len(tokens) < 2 or len(tokens[-1]) < 4:
        return None
    return tokens[-1]


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
            surfaces.extend(_registry_alias_surfaces(source_text, row))
        if not surfaces:
            surnames = {surname for row in rows if (surname := _registry_surname(row))}
            for surname in surnames:
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


def _registry_alias_occurs(source_text: str, row: Mapping[str, Any]) -> bool:
    """Apply the registry matching policy before generic morphology.

    A state-body alias whose every occurrence names a foreign institution (``Міноборони рф``)
    does not admit the Ukrainian registry entity. Aliases that coincide with common words
    (``Голос``, ``ЧЕСНО``) are matched like any other alias; Pass 1 decides whether a match
    names the registry actor.
    """
    alias = cast(str, row["alias"])
    if not alias_occurs(source_text, alias):
        return False
    if row.get("coarse_type") != "state_institution":
        return True
    surfaces = _alias_surfaces(source_text, alias)
    return not surfaces or any(
        not foreign_state_context(source_text, start, start + len(surface))
        for start, surface in surfaces
    )


def _registry_alias_surfaces(source_text: str, row: Mapping[str, Any]) -> list[tuple[int, str]]:
    """Find source spans admitted by the corresponding registry alias policy."""
    surfaces = _alias_surfaces(source_text, cast(str, row["alias"]))
    if row.get("coarse_type") != "state_institution":
        return surfaces
    return [
        (start, surface)
        for start, surface in surfaces
        if not foreign_state_context(source_text, start, start + len(surface))
    ]


def resolve_registry_mention(
    mention: str, aliases: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    """Return the unique registry row for one mention, or ``None`` when ambiguous/unresolved."""
    normalized = normalize_match_text(mention)
    exact = [
        row
        for row in aliases
        if cast(str, row["normalized_alias"]) == normalized and _registry_alias_occurs(mention, row)
    ]
    matches = exact or [row for row in aliases if _registry_alias_occurs(mention, row)]
    entity_ids = {int(row["entity_id"]) for row in matches}
    if not entity_ids:
        surname_matches = [
            row
            for row in aliases
            if (surname := _registry_surname(row)) is not None and alias_occurs(mention, surname)
        ]
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
        forms.update(stem + suffix for suffix in ("ого", "ому", "им", "ым", "ім", "ом"))
        if normalized.endswith("ій"):
            forms.update(stem + suffix for suffix in ("ія", "ію", "ієм", "ієві"))
    elif normalized.endswith(("ая", "яя")):
        stem = normalized[:-2]
        forms.update(stem + suffix for suffix in ("ой", "ей", "ую", "юю", "ою", "ею"))
    elif normalized.endswith(("ое", "ее")):
        stem = normalized[:-2]
        forms.update(stem + suffix for suffix in ("ого", "его", "ому", "ему", "ым", "им", "ом"))
    elif normalized.endswith("ия"):
        stem = normalized[:-2]
        forms.update(stem + suffix for suffix in ("ии", "ию", "ией"))
    elif normalized.endswith("а"):
        stem = normalized[:-1]
        forms.update(stem + suffix for suffix in ("и", "і", "у", "ою", "е", "о", "ы", "ой"))
        if normalized.endswith(("ська", "цька", "зька", "на", "ва", "ла", "ра")):
            forms.update(stem + suffix for suffix in ("ої", "ій"))
    elif normalized.endswith("я"):
        stem = normalized[:-1]
        forms.update(stem + suffix for suffix in ("і", "ї", "и", "ю", "єю", "ею", "ей"))
    elif normalized.endswith("о"):
        stem = normalized[:-1]
        forms.update(stem + suffix for suffix in ("а", "у", "ом", "і", "е"))
    elif normalized.endswith("ість"):
        stem = normalized[:-4]
        forms.update(stem + suffix for suffix in ("ості", "істю"))
    elif normalized.endswith("ь"):
        stem = normalized[:-1]
        forms.update(stem + suffix for suffix in ("я", "ю", "ем", "єм", "і", "е"))
    elif re.search(r"[бвгґджзклмнпрстфхцчшщ]$", normalized):
        forms.update(
            normalized + suffix
            for suffix in ("а", "у", "ом", "ем", "ім", "им", "і", "ові", "еві", "е")
        )
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
    if pass_name == "classification":
        _sanitize_classification_rhetoric(sanitized, actions)
        return SanitizedPayload(sanitized, tuple(actions))
    if pass_name == "claims" and isinstance(sanitized.get("claims"), list):
        sanitized["claims"] = _sanitize_claims(
            cast(list[Any], sanitized["claims"]), source_text, entities, actions
        )
        return SanitizedPayload(sanitized, tuple(actions))
    if pass_name == "targets":
        if isinstance(sanitized.get("claims"), dict):
            sanitized["claims"] = _sanitize_target_decisions(
                cast(dict[str, Any], sanitized["claims"]), entities, actions
            )
        return SanitizedPayload(sanitized, tuple(actions))
    if pass_name == "candidates":
        if isinstance(sanitized.get("candidates"), dict):
            sanitized["candidates"] = _sanitize_candidate_decisions(
                cast(dict[str, Any], sanitized["candidates"]), entities, actions
            )
        return SanitizedPayload(sanitized, tuple(actions))
    if pass_name != "entities" or not isinstance(sanitized.get("entities"), list):
        return SanitizedPayload(sanitized, tuple(actions))
    groups: list[Any] = []
    claimed: set[str] = set()
    for candidate in sanitized["entities"]:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("mentions"), list):
            groups.append(candidate)
            continue
        mentions: list[Any] = []
        seen: set[str] = set()
        for mention in candidate["mentions"]:
            if not isinstance(mention, str):
                mentions.append(mention)
            elif mention in claimed:
                actions.append({"action": "dropped_cross_group_duplicate", "mention": mention})
            elif mention in source_text and mention not in seen:
                seen.add(mention)
                mentions.append(mention)
            elif mention in seen:
                actions.append({"action": "deduplicated_mention", "mention": mention})
            else:
                actions.append({"action": "dropped_ungrounded_mention", "mention": mention})
        claimed.update(seen)
        if mentions:
            candidate["mentions"] = mentions
            groups.append(candidate)
        else:
            actions.append({"action": "dropped_empty_entity_group"})
    sanitized["entities"] = groups
    return SanitizedPayload(sanitized, tuple(actions))


def _sanitize_candidate_decisions(
    decisions: dict[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Drop decisions for candidate IDs that were not supplied to the candidate pass."""
    known = {cast(str, candidate["candidate_id"]) for candidate in candidates}
    kept: dict[str, Any] = {}
    for identifier, decision in decisions.items():
        if identifier in known:
            kept[identifier] = decision
        else:
            actions.append({"action": "dropped_unknown_candidate", "candidate_id": identifier})
    return kept


def _sanitize_target_decisions(
    decisions: dict[str, Any],
    claims: Sequence[Mapping[str, Any]],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Keep decisions for supplied claims and only actor names offered for each claim."""
    allowed = {
        cast(str, claim["claim_id"]): set(cast(list[str], claim["actors"])) for claim in claims
    }
    kept: dict[str, Any] = {}
    for claim_id, decision in decisions.items():
        if claim_id not in allowed:
            actions.append({"action": "dropped_unknown_claim", "claim_id": claim_id})
            continue
        if isinstance(decision, dict) and isinstance(decision.get("evaluated"), list):
            names: list[Any] = []
            for name in decision["evaluated"]:
                if name in names:
                    continue
                if isinstance(name, str) and name not in allowed[claim_id]:
                    actions.append(
                        {"action": "dropped_unoffered_actor", "claim_id": claim_id, "actor": name}
                    )
                    continue
                names.append(name)
            decision = {**decision, "evaluated": names}
        kept[claim_id] = decision
    return kept


def _sanitize_classification_rhetoric(
    payload: dict[str, Any], actions: list[dict[str, Any]]
) -> None:
    """Clear rhetoric forbidden by the stance contract without changing stance."""
    rows = payload.get("classifications")
    if not isinstance(rows, list):
        return
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        is_non_negative = row.get("stance") in {"позитивне", "відсутнє"}
        if is_non_negative and isinstance(row.get("rhetoric"), list):
            if row["rhetoric"]:
                row["rhetoric"] = []
                actions.append(
                    {"action": "cleared_rhetoric_for_non_negative_stance", "index": index}
                )


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


def generation_schema(pass_name: PassName, request: Mapping[str, Any]) -> dict[str, Any]:
    """Return the guided-generation schema for one concrete pass request.

    The candidate pass names every supplied registry candidate as a required property, so
    constrained decoding cannot skip or invent a candidate decision.
    """
    schema = deepcopy(load_inference_schema(pass_name))
    claims = request.get("claims")
    if pass_name == "targets" and isinstance(claims, list):
        decision = schema["properties"]["claims"]["additionalProperties"]
        properties = {}
        for claim in claims:
            claim_decision = deepcopy(decision)
            claim_decision["properties"]["evaluated"]["items"] = {
                "type": "string",
                "enum": list(claim["actors"]),
            }
            properties[cast(str, claim["claim_id"])] = claim_decision
        schema["properties"]["claims"] = {
            "type": "object",
            "additionalProperties": False,
            "required": list(properties),
            "properties": properties,
        }
        return schema
    candidates = request.get("candidates")
    if pass_name == "candidates" and isinstance(candidates, list):
        identifiers = [cast(str, candidate["candidate_id"]) for candidate in candidates]
        decision = schema["properties"]["candidates"]["additionalProperties"]
        schema["properties"]["candidates"] = {
            "type": "object",
            "additionalProperties": False,
            "required": identifiers,
            "properties": {identifier: decision for identifier in identifiers},
        }
    return schema


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
    if pass_name == "candidates":
        _validate_candidates(payload, entities)
    elif pass_name == "targets":
        _validate_targets(payload, entities)
    elif pass_name == "entities":
        _validate_entities(payload, source_text)
    elif pass_name == "claims":
        _validate_claims(payload, source_text, entities)
    else:
        _validate_classifications(payload, entities, claims)


def _validate_candidates(
    payload: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]
) -> None:
    """Require exactly one decision for every supplied registry candidate."""
    expected = [cast(str, candidate["candidate_id"]) for candidate in candidates]
    decided = list(cast(Mapping[str, Any], payload["candidates"]))
    issues = [
        ValidationIssue("reference_failure", f"missing candidate: {identifier}")
        for identifier in expected
        if identifier not in decided
    ]
    issues.extend(
        ValidationIssue("reference_failure", f"unexpected candidate decision: {identifier}")
        for identifier in decided
        if identifier not in expected
    )
    if issues:
        raise InferenceValidationError(issues)


def _validate_targets(payload: Mapping[str, Any], claims: Sequence[Mapping[str, Any]]) -> None:
    """Require one decision per supplied claim, naming only actors offered for it."""
    issues: list[ValidationIssue] = []
    decisions = cast(Mapping[str, Mapping[str, Any]], payload["claims"])
    for claim in claims:
        claim_id = cast(str, claim["claim_id"])
        if claim_id not in decisions:
            issues.append(ValidationIssue("reference_failure", f"missing claim: {claim_id}"))
            continue
        allowed = set(cast(list[str], claim["actors"]))
        for name in cast(list[str], decisions[claim_id]["evaluated"]):
            if name not in allowed:
                issues.append(
                    ValidationIssue(
                        "reference_failure", f"actor {name!r} not offered in {claim_id}"
                    )
                )
    known = {cast(str, claim["claim_id"]) for claim in claims}
    issues.extend(
        ValidationIssue("reference_failure", f"unexpected claim decision: {claim_id}")
        for claim_id in decisions
        if claim_id not in known
    )
    if issues:
        raise InferenceValidationError(issues)


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
