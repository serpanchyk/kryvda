"""Convert quote-anchored golden_v0 annotations into import payloads and validate them.

Annotators write exact quotes instead of character offsets; this module resolves the quotes to
half-open spans and applies the same import and full-record checks as the annotation editor.

Usage (from the repository root):
  uv run python experiments/datasets/golden_v0/src/golden_v0_anchor.py check-dir <batch_dir>
  uv run python experiments/datasets/golden_v0/src/golden_v0_anchor.py to-anchor <example_id>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from golden_v0_validation import DATASET_DIRECTORY, _semantic_errors, load_schema
from jsonschema import Draft202012Validator, FormatChecker

IMPORT_SCHEMA_PATH = DATASET_DIRECTORY / "annotation_import_schema_v1.json"
ANNOTATIONS_PATH = DATASET_DIRECTORY / "data" / "annotations.jsonl"
SOURCE_FIELDS = (
    "post_revision_id",
    "raw_post_id",
    "channel_id",
    "channel_reference",
    "telegram_message_id",
    "published_at",
    "text",
)


class AnchorError(ValueError):
    """Raised when a quote cannot be resolved in the post text."""


def locate(text: str, quote: Any, label: str) -> dict[str, int]:
    """Resolve a quote to a half-open span.

    Args:
        text: Post text.
        quote: Exact string, or ``{"text": ..., "occurrence": N}`` for a later repetition.
        label: Context used in error messages.

    Returns:
        Span selecting the requested occurrence.
    """
    occurrence = 1
    if isinstance(quote, dict):
        occurrence = int(quote.get("occurrence", 1))
        quote = quote.get("text")
    if not isinstance(quote, str) or not quote:
        raise AnchorError(f"{label}: quote must be a non-empty string")
    if occurrence < 1:
        raise AnchorError(f"{label}: occurrence must be at least 1")
    start = -1
    for _ in range(occurrence):
        start = text.find(quote, start + 1)
        if start < 0:
            raise AnchorError(
                f"{label}: quote {quote[:80]!r} occurrence {occurrence} not found "
                f"(found {text.count(quote)} time(s)); copy it character-for-character"
            )
    return {"start": start, "end": start + len(quote)}


def to_payload(anchor: dict[str, Any], text: str) -> dict[str, Any]:
    """Convert an anchor annotation into an annotation_import_schema_v1 payload.

    Args:
        anchor: Quote-anchored annotation.
        text: Post text the quotes refer to.

    Returns:
        Import payload with resolved spans.
    """
    annotations = anchor.get("annotations", {})
    entities = [
        {
            "id": entity.get("id"),
            "mention_span": locate(
                text,
                {"text": entity.get("surface_form"), "occurrence": entity.get("occurrence", 1)},
                f"entity {entity.get('id')}",
            ),
            "surface_form": entity.get("surface_form"),
            "canonical_name": entity.get("canonical_name"),
            "entity_type": entity.get("entity_type"),
            "subject_role": entity.get("subject_role"),
        }
        for entity in annotations.get("entities", [])
    ]
    stances = [
        {
            "entity_id": stance.get("entity_id"),
            "perspective": stance.get("perspective"),
            "value": stance.get("value"),
            "evidence_spans": [
                locate(text, quote, f"stance {stance.get('entity_id')}")
                for quote in stance.get("evidence", [])
            ],
        }
        for stance in annotations.get("stances", [])
    ]
    claims = [
        {
            "id": claim.get("id"),
            "normalized_text": claim.get("normalized_text"),
            "entity_ids": claim.get("entity_ids"),
            "evidence_spans": [
                locate(text, quote, f"claim {claim.get('id')}")
                for quote in claim.get("evidence", [])
            ],
            "attribution": claim.get("attribution"),
            "presentation": claim.get("presentation"),
            "epistemic_status": claim.get("epistemic_status"),
        }
        for claim in annotations.get("claims", [])
    ]
    features = []
    for feature in annotations.get("rhetorical_features", []):
        item = {
            "feature_type": feature.get("feature_type"),
            "evidence_span": locate(
                text, feature.get("evidence"), f"feature {feature.get('feature_type')}"
            ),
            "perspective": feature.get("perspective"),
        }
        for key in ("target_entity_id", "target_claim_id"):
            if feature.get(key) is not None:
                item[key] = feature[key]
        features.append(item)
    return {
        "selection": anchor.get("selection"),
        "annotations": {
            "entities": entities,
            "stances": stances,
            "claims": claims,
            "rhetorical_features": features,
        },
    }


def _overlaps(first: dict[str, int], second: dict[str, int]) -> bool:
    return first["start"] < second["end"] and second["start"] < first["end"]


def payload_errors(payload: dict[str, Any], post: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Validate an import payload as the editor would, plus evaluation-mapping warnings.

    Args:
        payload: Import payload produced by :func:`to_payload`.
        post: Frozen post source fields.

    Returns:
        Blocking errors and non-blocking warnings.
    """
    import_validator = Draft202012Validator(
        json.loads(IMPORT_SCHEMA_PATH.read_text(encoding="utf-8")), format_checker=FormatChecker()
    )
    errors = [
        f"import schema: {'/'.join(map(str, error.absolute_path))}: {error.message}"
        for error in import_validator.iter_errors(payload)
    ]
    if errors:
        return errors, []
    record = {
        "example_id": "golden_v0-999",
        "schema_version": "annotation_schema_v1",
        "source": {key: post[key] for key in SOURCE_FIELDS},
        "selection": payload["selection"],
        "annotations": json.loads(json.dumps(payload["annotations"])),
    }
    for entity in record["annotations"]["entities"]:
        name = entity.pop("canonical_name")
        entity.update(
            registry_entity_id=None if name is None else "local-0",
            canonical_name=None if name is None else " ".join(name.split()),
            registry_status="candidate",
            resolution_source="unresolved" if name is None else "registry",
        )
    full_validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    errors += [
        f"record schema: {'/'.join(map(str, error.absolute_path))}: {error.message}"
        for error in full_validator.iter_errors(record)
    ]
    errors += _semantic_errors(record, 1)
    annotations = payload["annotations"]
    perspectives = [("stance", item["perspective"]) for item in annotations["stances"]]
    perspectives += [("claim", item["attribution"]) for item in annotations["claims"]]
    perspectives += [
        ("feature", item["perspective"]) for item in annotations["rhetorical_features"]
    ]
    for label, perspective in perspectives:
        if perspective["source_kind"] == "named_entity" and not perspective.get("source_entity_id"):
            errors.append(f"{label}: named_entity perspective requires source_entity_id")
    return errors, _mapping_warnings(annotations)


def _mapping_warnings(annotations: dict[str, Any]) -> list[str]:
    """Flag annotations the canonical evaluation adapter cannot map unambiguously."""
    warnings: list[str] = []
    claimed = {entity_id for claim in annotations["claims"] for entity_id in claim["entity_ids"]}
    sources = {claim["attribution"].get("source_entity_id") for claim in annotations["claims"]}
    claim_ids = {claim["id"] for claim in annotations["claims"]}
    for entity in annotations["entities"]:
        if entity["subject_role"] == "primary" and entity["id"] not in claimed:
            warnings.append(f"primary entity {entity['id']} participates in no claim")
        elif entity["id"] not in claimed | sources:
            warnings.append(f"entity {entity['id']} is neither in a claim nor a claim source")
    for claim in annotations["claims"]:
        for entity_id in claim["entity_ids"]:
            stances = [s for s in annotations["stances"] if s["entity_id"] == entity_id]
            if not stances:
                warnings.append(f"claim {claim['id']} entity {entity_id} has no stance record")
                continue
            matching = [
                stance
                for stance in stances
                if stance["perspective"] == claim["attribution"]
                and any(
                    _overlaps(span, evidence)
                    for span in stance["evidence_spans"]
                    for evidence in claim["evidence_spans"]
                )
            ]
            if len(matching) != 1:
                warnings.append(
                    f"claim {claim['id']} entity {entity_id}: {len(matching)} stance records "
                    "share its attribution and overlap its evidence (expected exactly 1)"
                )
    for feature in annotations["rhetorical_features"]:
        if feature.get("target_claim_id") not in claim_ids:
            warnings.append(f"feature {feature['feature_type']} has no target_claim_id")
    return warnings


def check(anchor_path: Path, post: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Load, convert, and validate one anchor file."""
    try:
        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [f"invalid JSON: {error}"], []
    try:
        payload = to_payload(anchor, post["text"])
    except (AnchorError, AttributeError, TypeError, ValueError) as error:
        return [str(error)], []
    return payload_errors(payload, post)


def to_anchor(record: dict[str, Any]) -> dict[str, Any]:
    """Render a completed golden record in the anchor format.

    Args:
        record: Completed annotation_schema_v1 record.

    Returns:
        Equivalent quote-anchored annotation.
    """
    text = record["source"]["text"]

    def quote(span: dict[str, int]) -> Any:
        value = text[span["start"] : span["end"]]
        occurrence = text[: span["start"]].count(value) + 1
        return value if occurrence == 1 else {"text": value, "occurrence": occurrence}

    def entity(item: dict[str, Any]) -> dict[str, Any]:
        mention = quote(item["mention_span"])
        result = {"id": item["id"], "surface_form": item["surface_form"]}
        if isinstance(mention, dict):
            result["occurrence"] = mention["occurrence"]
        for key in ("canonical_name", "entity_type", "subject_role"):
            result[key] = item[key]
        return result

    annotations = record["annotations"]
    return {
        "selection": record["selection"],
        "annotations": {
            "entities": [entity(item) for item in annotations["entities"]],
            "stances": [
                {
                    "entity_id": item["entity_id"],
                    "perspective": item["perspective"],
                    "value": item["value"],
                    "evidence": [quote(span) for span in item["evidence_spans"]],
                }
                for item in annotations["stances"]
            ],
            "claims": [
                {
                    "id": item["id"],
                    "normalized_text": item["normalized_text"],
                    "entity_ids": item["entity_ids"],
                    "evidence": [quote(span) for span in item["evidence_spans"]],
                    "attribution": item["attribution"],
                    "presentation": item["presentation"],
                    "epistemic_status": item["epistemic_status"],
                }
                for item in annotations["claims"]
            ],
            "rhetorical_features": [
                {
                    "feature_type": item["feature_type"],
                    "evidence": quote(item["evidence_span"]),
                    **{
                        key: item[key]
                        for key in ("target_entity_id", "target_claim_id")
                        if key in item
                    },
                    "perspective": item["perspective"],
                }
                for item in annotations["rhetorical_features"]
            ],
        },
    }


def check_directory(batch: Path) -> list[str]:
    """Validate every expected output of a batch directory.

    Args:
        batch: Directory containing ``posts.json`` and ``out/<post_revision_id>.json``.

    Returns:
        Report lines; lines starting with a post ID followed by ``FAIL`` or ``MISSING`` block.
    """
    posts = json.loads((batch / "posts.json").read_text(encoding="utf-8"))
    lines: list[str] = []
    for post in posts:
        key = str(post["post_revision_id"])
        path = batch / "out" / f"{key}.json"
        if not path.exists():
            lines.append(f"{key}: MISSING")
            continue
        errors, warnings = check(path, post)
        status = "OK" if not errors else "FAIL"
        lines.append(f"{key}: {status} ({len(errors)} errors, {len(warnings)} warnings)")
        lines.extend(f"   ERROR {line}" for line in errors)
        lines.extend(f"   WARN  {line}" for line in warnings)
    return lines


def main() -> int:
    """Run the anchor tool command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-dir").add_argument("batch", type=Path)
    commands.add_parser("to-anchor").add_argument("example_id")
    args = parser.parse_args()
    if args.command == "check-dir":
        lines = check_directory(args.batch)
        print("\n".join(lines))
        return int(any(" FAIL " in f" {line} " or "MISSING" in line for line in lines))
    for line in ANNOTATIONS_PATH.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["example_id"] == args.example_id:
            print(json.dumps(to_anchor(record), ensure_ascii=False, indent=1))
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
