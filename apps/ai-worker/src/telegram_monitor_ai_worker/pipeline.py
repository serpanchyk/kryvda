"""Deterministic transformations between inference-v3 semantic passes."""

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from monitoring_common.contracts import (
    matched_registry_entities,
    resolve_registry_mention,
    sanitize_pass_payload_with_actions,
)
from monitoring_common.contracts import matched_registry_entity_ids as matched_registry_ids


def matched_monitored_entity_ids(post_text: str, aliases: Sequence[Mapping[str, Any]]) -> list[int]:
    """Return stable registry IDs whose active aliases occur in source text."""
    return matched_registry_ids(post_text, aliases)


def prefilter_entity_groups(
    post_text: str, aliases: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Create non-optional monitored entity groups from prefilter matches."""
    matches = matched_registry_entities(post_text, aliases)
    return [{"mentions": item["mentions"]} for item in matches]


def classification_subset(
    payload: Mapping[str, Any],
    entities: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[tuple[str, str]], list[dict[str, Any]]]:
    """Retain valid expected classification rows and identify pairs still needing a retry."""
    monitored = {str(entity["id"]) for entity in entities if bool(entity["monitored"])}
    expected = [
        (str(claim["id"]), entity_id)
        for claim in claims
        for entity_id in cast(list[str], claim["entity_ids"])
        if entity_id in monitored
    ]
    sanitized_result = sanitize_pass_payload_with_actions("classification", payload, "", ())
    sanitized_payload = sanitized_result.payload
    retained: list[dict[str, Any]] = []
    actions = list(sanitized_result.actions)
    seen: set[tuple[str, str]] = set()
    rows = sanitized_payload.get("classifications")
    if not isinstance(rows, list):
        return retained, expected, [{"action": "invalid_classification_payload"}]
    rhetoric_labels = {
        "корупція_або_особиста_вигода",
        "злочинна_або_незаконна_поведінка",
        "делегітимізація",
        "лицемірство_або_подвійні_стандарти",
        "висміювання_або_особиста_образа",
        "зовнішній_контроль_або_нелояльність",
    }
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            actions.append(
                {"action": "dropped_classification", "index": index, "reason": "not_object"}
            )
            continue
        pair = (row.get("claim_id"), row.get("entity_id"))
        rhetoric = row.get("rhetoric")
        valid = (
            isinstance(pair[0], str)
            and isinstance(pair[1], str)
            and pair in expected
            and pair not in seen
            and row.get("stance") in {"позитивне", "негативне", "відсутнє"}
            and isinstance(rhetoric, list)
            and all(isinstance(item, str) and item in rhetoric_labels for item in rhetoric)
            and len(rhetoric) == len(set(rhetoric))
            and (row.get("stance") == "негативне" or not rhetoric)
        )
        if not valid:
            actions.append(
                {"action": "dropped_classification", "index": index, "reason": "invalid_pair"}
            )
            continue
        seen.add(cast(tuple[str, str], pair))
        retained.append(dict(row))
    return retained, [pair for pair in expected if pair not in seen], actions


def classification_batches(
    items: Sequence[Mapping[str, Any]], batch_size: int
) -> list[list[dict[str, Any]]]:
    """Split classification items into stable, bounded provider requests."""
    if batch_size < 1:
        raise ValueError("classification batch size must be at least one")
    return [
        [dict(item) for item in items[index : index + batch_size]]
        for index in range(0, len(items), batch_size)
    ]


def salvage_classification_objects(raw_output: str) -> list[dict[str, Any]]:
    """Recover only complete objects from a truncated classifications array.

    This deliberately accepts a contiguous JSON-object prefix of the generated array. It never
    closes brackets, fills fields, or searches beyond malformed content, so recovery cannot alter
    the model's semantic output.
    """
    match = re.search(r'"classifications"\s*:\s*\[', raw_output)
    if match is None:
        return []
    decoder = json.JSONDecoder()
    position = match.end()
    recovered: list[dict[str, Any]] = []
    while position < len(raw_output):
        while position < len(raw_output) and raw_output[position].isspace():
            position += 1
        if position < len(raw_output) and raw_output[position] == ",":
            position += 1
            continue
        if position >= len(raw_output) or raw_output[position] == "]":
            break
        if raw_output[position] != "{":
            break
        try:
            value, position = decoder.raw_decode(raw_output, position)
        except json.JSONDecodeError:
            break
        if not isinstance(value, dict):
            break
        recovered.append(value)
    return recovered


def resolve_entity_groups(
    groups: Sequence[Mapping[str, Any]], aliases: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Resolve exact aliases, merge safe duplicates, and assign local IDs."""
    resolved: list[dict[str, Any]] = []
    by_registry_id: dict[int, dict[str, Any]] = {}
    for group in groups:
        mentions = cast(list[str], group["mentions"])
        partitions: dict[int | None, list[str]] = {}
        for mention in mentions:
            row = resolve_registry_mention(mention, aliases)
            registry_id = int(row["entity_id"]) if row is not None else None
            partitions.setdefault(registry_id, []).append(mention)
        for registry_id, partition_mentions in partitions.items():
            if registry_id is not None:
                row = next(row for row in aliases if int(row["entity_id"]) == registry_id)
                existing = by_registry_id.get(registry_id)
                if existing is not None:
                    existing_mentions = cast(list[str], existing["mentions"])
                    existing_mentions.extend(
                        mention
                        for mention in partition_mentions
                        if mention not in existing_mentions
                    )
                    continue
                entity = {
                    "mentions": list(partition_mentions),
                    "registry_entity_id": registry_id,
                    "canonical_name": row["canonical_name"],
                    "monitored": bool(row["monitored"]),
                }
                by_registry_id[registry_id] = entity
            else:
                entity = {
                    "mentions": list(partition_mentions),
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
    status: str = "completed",
    degradations: Sequence[Mapping[str, Any]] = (),
    pipeline_version: str = "inference_v3_5_2",
) -> dict[str, Any]:
    """Build the inspectable immutable v3 result document."""
    return {
        "pipeline_version": pipeline_version,
        "status": status,
        "degradations": [dict(item) for item in degradations],
        "entities": [dict(entity) for entity in entities],
        "claims": [dict(claim) for claim in claims],
        "classifications": [dict(row) for row in classifications],
    }
