"""Deterministic transformations between inference-v3 semantic passes."""

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from monitoring_common.contracts import (
    InferenceValidationError,
    ValidationIssue,
    alias_occurs,
    normalize_match_text,
)


def matched_monitored_entity_ids(post_text: str, aliases: Sequence[Mapping[str, Any]]) -> list[int]:
    """Return stable registry IDs whose active aliases occur in source text."""
    return sorted(
        {
            int(row["entity_id"])
            for row in aliases
            if bool(row["monitored"]) and alias_occurs(post_text, cast(str, row["alias"]))
        }
    )


def resolve_entity_groups(
    groups: Sequence[Mapping[str, Any]], aliases: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Resolve exact aliases, merge safe duplicates, and assign local IDs."""
    aliases_by_normalized: dict[str, Mapping[str, Any]] = {
        cast(str, row["normalized_alias"]): row for row in aliases
    }
    resolved: list[dict[str, Any]] = []
    by_registry_id: dict[int, dict[str, Any]] = {}
    for group in groups:
        mentions = cast(list[str], group["mentions"])
        matched_rows = {
            int(row["entity_id"]): row
            for mention in mentions
            if (row := aliases_by_normalized.get(normalize_match_text(mention))) is not None
        }
        if len(matched_rows) > 1:
            raise InferenceValidationError(
                [
                    ValidationIssue(
                        "reference_failure",
                        "one entity group resolves to multiple registry entities",
                    )
                ]
            )
        if matched_rows:
            registry_id, row = next(iter(matched_rows.items()))
            existing = by_registry_id.get(registry_id)
            if existing is not None:
                existing_mentions = cast(list[str], existing["mentions"])
                existing_mentions.extend(
                    mention for mention in mentions if mention not in existing_mentions
                )
                continue
            entity = {
                "mentions": list(mentions),
                "registry_entity_id": registry_id,
                "canonical_name": row["canonical_name"],
                "monitored": bool(row["monitored"]),
            }
            by_registry_id[registry_id] = entity
        else:
            entity = {
                "mentions": list(mentions),
                "registry_entity_id": None,
                "canonical_name": None,
                "monitored": False,
            }
        resolved.append(entity)
    for index, entity in enumerate(resolved, start=1):
        entity["id"] = f"e{index}"
    return resolved


def assign_claim_ids(payload: Mapping[str, Any], source_text: str) -> list[dict[str, Any]]:
    """Assign local claim IDs and earliest deterministic evidence offsets."""
    claims: list[dict[str, Any]] = []
    for index, value in enumerate(cast(list[Mapping[str, Any]], payload["claims"]), start=1):
        claim = dict(value)
        evidence = cast(str, claim["evidence_text"])
        start = source_text.find(evidence)
        claim.update(
            {
                "id": f"c{index}",
                "evidence_start": start,
                "evidence_end": start + len(evidence),
            }
        )
        claims.append(claim)
    return claims


def classification_items(
    source_text: str,
    entities: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build one context-rich item per monitored claim-target pair."""
    entities_by_id = {cast(str, entity["id"]): entity for entity in entities}
    items: list[dict[str, Any]] = []
    for claim in claims:
        for entity_id in cast(list[str], claim["entity_ids"]):
            entity = entities_by_id[entity_id]
            if not bool(entity["monitored"]):
                continue
            items.append(
                {
                    "claim_id": claim["id"],
                    "entity_id": entity_id,
                    "target": entity["canonical_name"] or cast(list[str], entity["mentions"])[0],
                    "normalized_claim": claim["normalized_text"],
                    "evidence_text": claim["evidence_text"],
                    "local_context": local_context(
                        source_text,
                        cast(int, claim["evidence_start"]),
                        cast(int, claim["evidence_end"]),
                    ),
                }
            )
    return items


def local_context(source_text: str, evidence_start: int, evidence_end: int) -> str:
    """Return evidence sentences plus one neighboring sentence on either side."""
    boundaries = [0]
    boundaries.extend(match.end() for match in re.finditer(r"(?:[.!?…]+\s+|\n+)", source_text))
    if boundaries[-1] != len(source_text):
        boundaries.append(len(source_text))
    segments = [
        (start, end)
        for start, end in zip(boundaries, boundaries[1:])
        if source_text[start:end].strip()
    ]
    containing = [
        index
        for index, (start, end) in enumerate(segments)
        if start < evidence_end and evidence_start < end
    ]
    if not containing:
        return source_text[evidence_start:evidence_end]
    first = max(containing[0] - 1, 0)
    last = min(containing[-1] + 1, len(segments) - 1)
    return source_text[segments[first][0] : segments[last][1]].strip()


def final_payload(
    entities: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
    classifications: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the inspectable immutable v3 result document."""
    return {
        "pipeline_version": "inference_v3",
        "entities": [dict(entity) for entity in entities],
        "claims": [dict(claim) for claim in claims],
        "classifications": [dict(row) for row in classifications],
    }
