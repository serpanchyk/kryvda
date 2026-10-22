"""Deterministic transformations between inference-v3 semantic passes."""

import json
import re
from collections.abc import Collection, Mapping, Sequence
from typing import Any, cast

from monitoring_common.contracts import (
    matched_registry_entities,
    mention_is_only_foreign_state,
    resolve_registry_mention,
    sanitize_pass_payload_with_actions,
)
from monitoring_common.contracts import matched_registry_entity_ids as matched_registry_ids

PIPELINE_VERSION = "inference_v4_8"


def matched_monitored_entity_ids(post_text: str, aliases: Sequence[Mapping[str, Any]]) -> list[int]:
    """Return stable registry IDs whose active aliases occur in source text."""
    return matched_registry_ids(post_text, aliases)


def registry_candidates(
    post_text: str, aliases: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Describe every prefilter registry match as a candidate to confirm or reject.

    An alias match is only lexical evidence: ``голос`` or ``чесно`` can be ordinary words, so the
    candidate pass decides whether the matched forms name the registry actor.
    """
    types = {int(row["entity_id"]): row.get("coarse_type") for row in aliases}
    return [
        {
            "candidate_id": f"r{index}",
            "entity_id": int(match["entity_id"]),
            "name": match["canonical_name"],
            "type": types.get(int(match["entity_id"])),
            "mentions": list(match["mentions"]),
        }
        for index, match in enumerate(matched_registry_entities(post_text, aliases), start=1)
    ]


def candidate_request(
    post_text: str, candidates: Sequence[Mapping[str, Any]], max_contexts: int = 3
) -> dict[str, Any]:
    """Build the candidate-pass request: each candidate with the sentences around its forms."""
    items = []
    for candidate in candidates:
        contexts: list[str] = []
        for mention in cast(list[str], candidate["mentions"]):
            start = post_text.find(mention)
            while start != -1 and len(contexts) < max_contexts:
                context = local_context(post_text, start, start + len(mention))
                if context not in contexts:
                    contexts.append(context)
                start = post_text.find(mention, start + 1)
        items.append(
            {
                "candidate_id": candidate["candidate_id"],
                "name": candidate["name"],
                "type": candidate["type"],
                "mentions": candidate["mentions"],
                "contexts": contexts,
            }
        )
    return {"candidates": items}


def admitted_entities(
    candidates: Sequence[Mapping[str, Any]],
    decisions: Mapping[str, Any] | None,
    model_groups: Sequence[Mapping[str, Any]],
    aliases: Sequence[Mapping[str, Any]],
    source_text: str,
) -> list[dict[str, Any]]:
    """Resolve Pass 1 groups together with the registry candidates the model confirmed.

    Without valid candidate decisions every candidate is admitted, which matches the
    pre-v3.7 behaviour. A rejected candidate cannot re-enter through a Pass 1 group that
    repeats one of its forms.
    """
    if decisions is None:
        confirmed = {cast(str, candidate["candidate_id"]) for candidate in candidates}
    else:
        confirmed = {
            identifier
            for identifier, decision in cast(Mapping[str, Any], decisions["candidates"]).items()
            if cast(Mapping[str, Any], decision)["same_actor"] is True
        }
    groups: list[Mapping[str, Any]] = [
        {"mentions": candidate["mentions"]}
        for candidate in candidates
        if candidate["candidate_id"] in confirmed
    ]
    rejected = {
        int(candidate["entity_id"])
        for candidate in candidates
        if candidate["candidate_id"] not in confirmed
    }
    groups.extend(model_groups)
    return resolve_entity_groups(groups, aliases, source_text, rejected)


def focused_claim_request(
    post_text: str, entities: Sequence[Mapping[str, Any]], focus: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a Pass 2 request that asks only what the post says about one monitored entity."""
    return {
        "post_text": post_text,
        "entities": list(entities),
        "focus_entity_id": focus["id"],
        "focus_entity": _entity_label(focus),
    }


def merge_focused_claims(payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Merge per-entity Pass 2 outputs, uniting claims that quote the same evidence.

    Two focused calls often extract the same statement; a claim with the same evidence and
    source as an earlier one only adds its entity IDs to that claim.
    """
    merged: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str, Any], dict[str, Any]] = {}
    for payload in payloads:
        for claim in cast(list[Mapping[str, Any]], payload["claims"]):
            attribution = cast(Mapping[str, Any], claim["attribution"])
            key = (
                cast(str, claim["evidence_text"]),
                cast(str, attribution.get("source_kind")),
                attribution.get("source_entity_id"),
            )
            existing = by_key.get(key)
            if existing is None:
                copy = dict(claim)
                copy["entity_ids"] = list(cast(list[str], claim["entity_ids"]))
                by_key[key] = copy
                merged.append(copy)
                continue
            for entity_id in cast(list[str], claim["entity_ids"]):
                if entity_id not in existing["entity_ids"]:
                    existing["entity_ids"].append(entity_id)
    return {"claims": merged}


def has_monitored_entity(entities: Sequence[Mapping[str, Any]]) -> bool:
    """Tell whether any resolved entity still needs claim extraction."""
    return any(bool(entity["monitored"]) for entity in entities)


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
    """Recover only complete objects from a truncated classifications array."""
    return salvage_array_objects(raw_output, "classifications")


def salvage_entity_payload(raw_output: str) -> dict[str, Any] | None:
    """Recover the complete entity groups that precede a broken Pass 1 response.

    Mamay can loop on a repeated name until the JSON breaks; the groups emitted before the loop
    are still the model's own output, and repair never sees the post.
    """
    if re.search(r'"entities"\s*:\s*\[', raw_output) is None:
        return None
    return {"entities": salvage_array_objects(raw_output, "entities")}


def salvage_array_objects(raw_output: str, key: str) -> list[dict[str, Any]]:
    """Recover only complete objects from a possibly truncated top-level JSON array.

    This deliberately accepts a contiguous JSON-object prefix of the generated array. It never
    closes brackets, fills fields, or searches beyond malformed content, so recovery cannot alter
    the model's semantic output.
    """
    match = re.search(rf'"{re.escape(key)}"\s*:\s*\[', raw_output)
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
    groups: Sequence[Mapping[str, Any]],
    aliases: Sequence[Mapping[str, Any]],
    source_text: str | None = None,
    rejected_registry_ids: Collection[int] = (),
) -> list[dict[str, Any]]:
    """Resolve exact aliases, merge safe duplicates, and assign local IDs.

    With the source text, a state-body mention that only ever names a foreign institution
    (``Міноборони`` in ``Міноборони рф``) stays an unresolved post-local actor, as does a
    mention of a registry entity that Pass 1 rejected.
    """
    resolved: list[dict[str, Any]] = []
    by_registry_id: dict[int, dict[str, Any]] = {}
    for group in groups:
        mentions = cast(list[str], group["mentions"])
        partitions: dict[int | None, list[str]] = {}
        for mention in mentions:
            row = resolve_registry_mention(mention, aliases)
            if (
                row is not None
                and source_text is not None
                and row.get("coarse_type") == "state_institution"
                and mention_is_only_foreign_state(source_text, mention)
            ):
                row = None
            if row is not None and int(row["entity_id"]) in rejected_registry_ids:
                row = None
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
    """Build one context-rich item per monitored claim-target pair.

    Each item names the claim's responsible source so Pass 3 classifies that source's stance and
    can tell a target's self-presentation from another source's evaluation of it.
    """
    entities_by_id = {cast(str, entity["id"]): entity for entity in entities}
    items: list[dict[str, Any]] = []
    for claim in claims:
        attribution = cast(Mapping[str, Any], claim["attribution"])
        source_id = attribution.get("source_entity_id")
        claim_source = _claim_source_label(attribution, entities_by_id)
        for entity_id in cast(list[str], claim["entity_ids"]):
            entity = entities_by_id[entity_id]
            if not bool(entity["monitored"]):
                continue
            items.append(
                {
                    "claim_id": claim["id"],
                    "entity_id": entity_id,
                    "target": _entity_label(entity),
                    "claim_source": claim_source,
                    "source_is_target": source_id == entity_id,
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


OTHER_ACTOR = "інший актор або ніхто з переліку"


def target_request(
    items: Sequence[Mapping[str, Any]], entities: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Group Pass 3 pairs by claim for the targets pass, listing every actor of each claim.

    The options include non-monitored actors named in the claim and a catch-all, so the model can
    name the actor it actually means (a judge rather than her court) instead of being forced to
    pick the only monitored entity on offer. Options are names, the form the model reasons in.
    """
    claims: dict[str, dict[str, Any]] = {}
    for item in items:
        claim = claims.setdefault(
            cast(str, item["claim_id"]),
            {
                "claim_id": item["claim_id"],
                "claim_source": item["claim_source"],
                "normalized_claim": item["normalized_claim"],
                "evidence_text": item["evidence_text"],
                "local_context": item["local_context"],
                "actors": [],
            },
        )
        if item["target"] not in claim["actors"]:
            claim["actors"].append(item["target"])
    for claim in claims.values():
        text = f"{claim['normalized_claim']} {claim['evidence_text']}"
        for entity in entities:
            name = _entity_label(entity)
            if name in claim["actors"]:
                continue
            if any(mention in text for mention in cast(list[str], entity["mentions"])) or (
                entity["canonical_name"] and cast(str, entity["canonical_name"]) in text
            ):
                claim["actors"].append(name)
        claim["actors"].append(OTHER_ACTOR)
    return {"claims": list(claims.values())}


def split_by_targets(
    items: Sequence[Mapping[str, Any]], decisions: Mapping[str, Any] | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return pairs whose target the source evaluates, and `відсутнє` rows for the others.

    Without valid targets decisions every pair is classified, as before v4.
    """
    if decisions is None:
        return [dict(item) for item in items], []
    evaluated = {
        (claim_id, name)
        for claim_id, decision in cast(Mapping[str, Any], decisions["claims"]).items()
        for name in cast(Mapping[str, Any], decision)["evaluated"]
    }
    to_classify: list[dict[str, Any]] = []
    absent: list[dict[str, Any]] = []
    for item in items:
        if (item["claim_id"], item["target"]) in evaluated:
            to_classify.append(dict(item))
        else:
            absent.append(
                {
                    "claim_id": item["claim_id"],
                    "entity_id": item["entity_id"],
                    "stance": "відсутнє",
                    "rhetoric": [],
                }
            )
    return to_classify, absent


def affiliation_request(
    post_text: str, entities: Sequence[Mapping[str, Any]], aliases: Sequence[Mapping[str, Any]]
) -> dict[str, Any] | None:
    """Offer every non-organization actor and every monitored registry organization of a post.

    Returns ``None`` when the post has no person or no monitored organization to link.
    """
    kinds = {int(row["entity_id"]): row.get("coarse_type") for row in aliases}
    organizations: list[str] = []
    people: list[str] = []
    for entity in entities:
        registry_id = entity.get("registry_entity_id")
        is_org = registry_id is not None and kinds.get(int(registry_id)) not in (None, "person")
        label = _entity_label(entity)
        if is_org and entity.get("monitored"):
            organizations.append(label)
        elif not is_org and label not in people:
            people.append(label)
    if not organizations or not people:
        return None
    return {"post_text": post_text, "people": people, "organizations": organizations}


def affiliation_needed(
    request: Mapping[str, Any] | None,
    entities: Sequence[Mapping[str, Any]],
    classifications: Sequence[Mapping[str, Any]],
) -> bool:
    """Return whether any offered person received a negative stance worth propagating."""
    if request is None:
        return False
    people = {
        cast(str, entity["id"]) for entity in entities if _entity_label(entity) in request["people"]
    }
    return any(
        row["stance"] == "негативне" and row["entity_id"] in people for row in classifications
    )


def propagate_affiliations(
    claims: Sequence[Mapping[str, Any]],
    classifications: Sequence[Mapping[str, Any]],
    entities: Sequence[Mapping[str, Any]],
    decisions: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    """Carry a negative stance toward a person over to the organizations the post links them to.

    Criticism of a head, member or former employee is criticism of the organization when the
    post itself names that link; the organization is added to the claim and receives the same
    stance and rhetoric. Returns the claims, the classifications and every propagation made.
    """
    claims_out = [{**claim, "entity_ids": list(claim["entity_ids"])} for claim in claims]
    rows = [dict(row) for row in classifications]
    if not decisions:
        return claims_out, rows, []
    ids = {_entity_label(entity): cast(str, entity["id"]) for entity in entities}
    members: dict[str, list[str]] = {}
    for person, decision in cast(Mapping[str, Any], decisions["people"]).items():
        orgs = [ids[name] for name in decision["organizations"] if name in ids]
        if person in ids and orgs:
            members[ids[person]] = orgs
    by_claim = {cast(str, claim["id"]): claim for claim in claims_out}
    index = {(row["claim_id"], row["entity_id"]): row for row in rows}
    propagated: list[dict[str, str]] = []
    for row in list(rows):
        if row["stance"] != "негативне" or row["entity_id"] not in members:
            continue
        for org in members[row["entity_id"]]:
            existing = index.get((row["claim_id"], org))
            if existing is not None and existing["stance"] == "негативне":
                continue
            new = {
                "claim_id": row["claim_id"],
                "entity_id": org,
                "stance": "негативне",
                "rhetoric": list(row["rhetoric"]),
            }
            if existing is None:
                rows.append(new)
            else:
                existing.update(new)
            index[(row["claim_id"], org)] = existing or new
            claim = by_claim.get(cast(str, row["claim_id"]))
            if claim is not None and org not in claim["entity_ids"]:
                claim["entity_ids"].append(org)
            propagated.append({"claim_id": row["claim_id"], "from": row["entity_id"], "to": org})
    return claims_out, rows, propagated


def _entity_label(entity: Mapping[str, Any]) -> str:
    return cast(str, entity["canonical_name"] or cast(list[str], entity["mentions"])[0])


def _claim_source_label(
    attribution: Mapping[str, Any], entities_by_id: Mapping[str, Mapping[str, Any]]
) -> str:
    """Name the party responsible for a claim in the Ukrainian Pass 3 vocabulary."""
    source_id = attribution.get("source_entity_id")
    if attribution.get("source_kind") == "named_entity" and source_id in entities_by_id:
        return _entity_label(entities_by_id[cast(str, source_id)])
    if attribution.get("source_kind") == "external_unnamed":
        return "неназване джерело"
    return "канал"


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
    pipeline_version: str = PIPELINE_VERSION,
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
