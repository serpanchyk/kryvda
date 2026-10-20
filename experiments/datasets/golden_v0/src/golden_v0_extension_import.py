"""Measure agreement of quote-anchored annotations and import them into golden_v0.

Import goes through the annotation editor's own ``complete-import`` endpoint, so registry
candidates, validation, and exports are produced exactly as for a reviewed ChatGPT import.
The editor service must be stopped while this runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from golden_v0_extension import CALIBRATION_IDS, DATA, REPOSITORY, WORK

# Command-line runs need the sibling experiment packages that pytest adds via pythonpath.
for _source in ("experiments/dspy/src", "experiments/annotation-ui/src"):
    if str(REPOSITORY / _source) not in sys.path:
        sys.path.append(str(REPOSITORY / _source))

from golden_schema import CanonicalGolden, GoldenV0Adapter  # noqa: E402
from golden_v0_anchor import SOURCE_FIELDS, check, to_payload  # noqa: E402

PROVENANCE_FILE = "annotation_provenance.jsonl"
ANNOTATOR = "claude-opus-5-5"
LEGACY_ANNOTATOR = "chatgpt_with_web_access+partial_human_review"
# Spellings of one actor chosen differently by parallel annotators; the value is kept.
CANONICAL_VARIANTS = {
    "Дар’я Каленюк": "Дарія Каленюк",
    "Євгеній Хмара": "Євген Хмара",
    "Росія": "Російська Федерація",
}
# Actors the local registry lists under two types; the brief fixes one of them.
TYPE_OVERRIDES = {
    **dict.fromkeys(
        (
            "Руслан Кравченко",
            "Анатолій Шарій",
            "Ярослав Железняк",
            "Кирило Буданов",
            "Володимир Зеленський",
            "Андрій Єрмак",
            "Михайло Федоров",
            "Андрій Білецький",
        ),
        "person",
    ),
    "Слуга народу": "political_actor",
}


def normalize_entities(
    anchors: Iterable[dict[str, Any]], registry: Iterable[Mapping[str, Any]]
) -> None:
    """Make canonical names and types consistent across independently annotated posts.

    Variant spellings are merged, registry actors take their single registry type (or the
    brief's override), and new actors take the type most annotators chose for them.
    """
    anchors = list(anchors)
    registry_types: defaultdict[str, set[str]] = defaultdict(set)
    for entry in registry:
        registry_types[entry["canonical_name"]].add(entry["entity_type"])
    entities = [
        entity
        for anchor in anchors
        for entity in anchor["annotations"]["entities"]
        if entity.get("canonical_name")
    ]
    for entity in entities:
        name = " ".join(entity["canonical_name"].split())
        entity["canonical_name"] = CANONICAL_VARIANTS.get(name, name)
    observed = Counter((entity["canonical_name"], entity["entity_type"]) for entity in entities)
    for entity in entities:
        name = entity["canonical_name"]
        if name in TYPE_OVERRIDES:
            entity["entity_type"] = TYPE_OVERRIDES[name]
        elif len(registry_types[name]) == 1:
            entity["entity_type"] = next(iter(registry_types[name]))
        else:
            entity["entity_type"] = max(
                (count, entity_type)
                for (candidate, entity_type), count in observed.items()
                if candidate == name
            )[1]


def materialize(
    anchor: Mapping[str, Any], post: Mapping[str, Any], example_id: str
) -> dict[str, Any]:
    """Build a completed-record equivalent without touching the editor registry.

    Canonical names stand in for registry IDs, which is sufficient for semantic comparison.
    """
    payload = to_payload(dict(anchor), str(post["text"]))
    record = {
        "example_id": example_id,
        "schema_version": "annotation_schema_v1",
        "source": {field: post[field] for field in SOURCE_FIELDS},
        "selection": payload["selection"],
        "annotations": payload["annotations"],
    }
    for entity in record["annotations"]["entities"]:
        name = entity.pop("canonical_name")
        entity.update(
            registry_entity_id=name,
            canonical_name=name,
            registry_status="candidate",
            resolution_source="unresolved" if name is None else "registry",
        )
    return record


def _entity_labels(golden: CanonicalGolden) -> dict[str, dict[str, set[str]]]:
    """Summarise each named target entity as its stance and rhetoric label sets."""
    names = {
        entity.id: " ".join(entity.canonical_name.split()).casefold()
        for entity in golden.entities
        if entity.canonical_name
    }
    labels: dict[str, dict[str, set[str]]] = {}
    for item in golden.classifications:
        name = names.get(item.entity_id)
        if name is None:
            continue
        entry = labels.setdefault(name, {"stance": set(), "rhetoric": set()})
        if item.stance:
            entry["stance"].add(item.stance)
        entry["rhetoric"].update(item.rhetoric)
    return labels


def _f1(true_positive: int, predicted: int, expected: int) -> dict[str, float | None]:
    precision = true_positive / predicted if predicted else None
    recall = true_positive / expected if expected else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def agreement(pairs: Iterable[tuple[CanonicalGolden, CanonicalGolden]]) -> dict[str, Any]:
    """Compare reference and candidate annotations at target-entity level.

    Claims are not aligned one-to-one; instead each canonical target entity is reduced to the
    stance values and rhetoric labels it receives anywhere in the post.

    Args:
        pairs: (reference, candidate) canonical annotations of the same posts.

    Returns:
        Entity, negative-stance, and rhetoric agreement plus claim-count totals.
    """
    entity = [0, 0, 0]
    negative = [0, 0, 0]
    rhetoric = [0, 0, 0]
    stance_exact = shared = 0
    claims = [0, 0]
    for reference, candidate in pairs:
        expected, predicted = _entity_labels(reference), _entity_labels(candidate)
        common = expected.keys() & predicted.keys()
        entity[0] += len(common)
        entity[1] += len(predicted)
        entity[2] += len(expected)
        for name in common:
            shared += 1
            stance_exact += expected[name]["stance"] == predicted[name]["stance"]
        for name in expected.keys() | predicted.keys():
            gold = expected.get(name, {"stance": set(), "rhetoric": set()})
            pred = predicted.get(name, {"stance": set(), "rhetoric": set()})
            gold_negative = "негативне" in gold["stance"]
            pred_negative = "негативне" in pred["stance"]
            negative[0] += gold_negative and pred_negative
            negative[1] += pred_negative
            negative[2] += gold_negative
            rhetoric[0] += len(gold["rhetoric"] & pred["rhetoric"])
            rhetoric[1] += len(pred["rhetoric"])
            rhetoric[2] += len(gold["rhetoric"])
        claims[0] += len(reference.claims)
        claims[1] += len(candidate.claims)
    return {
        "target_entities": _f1(*entity),
        "negative_target": _f1(*negative),
        "rhetoric_labels": _f1(*rhetoric),
        "shared_entity_stance_set_exact": stance_exact / shared if shared else None,
        "claims": {"reference": claims[0], "candidate": claims[1]},
    }


def calibration_report(batch: Path, annotations: Path) -> dict[str, Any]:
    """Score a blind calibration batch against the reviewed records it re-annotates."""
    records = {
        record["source"]["post_revision_id"]: record
        for record in map(json.loads, annotations.read_text(encoding="utf-8").splitlines())
        if record["example_id"] in CALIBRATION_IDS
    }
    adapter = GoldenV0Adapter()
    pairs = []
    for post in json.loads((batch / "posts.json").read_text(encoding="utf-8")):
        reference = records[post["post_revision_id"]]
        anchor = json.loads(
            (batch / "out" / f"{post['post_revision_id']}.json").read_text(encoding="utf-8")
        )
        candidate = materialize(anchor, post, reference["example_id"])
        pairs.append((adapter.convert(reference), adapter.convert(candidate)))
    return agreement(pairs)


def import_batches(
    batches: Sequence[Path], data: Path, annotated_at: str, partition: str = "extension400"
) -> list[str]:
    """Complete validated batch outputs through the editor and record their provenance.

    Args:
        batches: Batch directories whose every output passes the anchor checks.
        data: golden_v0 data directory with ``editor.json``.
        annotated_at: ISO timestamp stored in the provenance records.
        partition: Provenance partition of the created examples.

    Returns:
        Example IDs created, in order.
    """
    from annotation_app import create_app
    from fastapi.testclient import TestClient

    work = []
    for batch in batches:
        for post in json.loads((batch / "posts.json").read_text(encoding="utf-8")):
            path = batch / "out" / f"{post['post_revision_id']}.json"
            errors, _ = check(path, post)
            if errors:
                raise ValueError(f"{path}: {errors[0]}")
            work.append((batch.name, post, json.loads(path.read_text(encoding="utf-8"))))
    state_path = data / "editor.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    normalize_entities((anchor for _, _, anchor in work), state["registry"])
    number = max(int(item["record"]["example_id"][-3:]) for item in state["records"].values())
    created: list[tuple[str, str, int]] = []
    for batch_name, post, _ in work:
        key = str(post["post_revision_id"])
        if key in state["records"]:
            raise ValueError(f"post revision {key} is already in the editor")
        number += 1
        if number > 999:
            raise ValueError("golden_v0 example ID capacity reached")
        example_id = f"golden_v0-{number:03}"
        state["records"][key] = {
            "version": 1,
            "status": "draft",
            "record": {
                "example_id": example_id,
                "schema_version": "annotation_schema_v1",
                "source": {field: post[field] for field in SOURCE_FIELDS},
                "selection": {"facets": [], "reason": ""},
                "annotations": {
                    "entities": [],
                    "stances": [],
                    "claims": [],
                    "rhetorical_features": [],
                },
            },
        }
        created.append((example_id, batch_name, int(key)))
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    client = TestClient(create_app(data))
    for _, post, anchor in work:
        response = client.post(
            f"/api/records/{post['post_revision_id']}/complete-import",
            json={"version": 1, "payload": to_payload(anchor, post["text"])},
        )
        if response.status_code != 200:
            raise ValueError(f"{post['post_revision_id']}: {response.json()}")
    _append_provenance(data, created, annotated_at, partition)
    return [example_id for example_id, _, _ in created]


def renormalize_imported(data: Path) -> list[str]:
    """Merge variant canonical names in already imported extension records via the editor.

    Returns:
        Example IDs whose entities were re-resolved.
    """
    from annotation_app import create_app
    from fastapi.testclient import TestClient

    provenance = data / PROVENANCE_FILE
    if not provenance.exists():
        return []
    extension = {
        row["example_id"]
        for row in map(json.loads, provenance.read_text(encoding="utf-8").splitlines())
        if row["partition"] == "extension400"
    }
    state = json.loads((data / "editor.json").read_text(encoding="utf-8"))
    by_name = {entry["canonical_name"]: entry for entry in state["registry"]}
    client = TestClient(create_app(data))
    changed = []
    for key, item in state["records"].items():
        record = item["record"]
        entities = [
            entity
            for entity in record["annotations"]["entities"]
            if record["example_id"] in extension
            and entity.get("canonical_name") in CANONICAL_VARIANTS
        ]
        if not entities:
            continue
        for entity in entities:
            entry = by_name[CANONICAL_VARIANTS[entity["canonical_name"]]]
            entity.update(
                canonical_name=entry["canonical_name"],
                registry_entity_id=entry["id"],
                entity_type=entry["entity_type"],
                registry_status=entry["status"],
            )
        response = client.put(
            f"/api/records/{key}",
            json={"record": record, "status": item["status"], "version": item["version"]},
        )
        if response.status_code != 200:
            raise ValueError(f"{record['example_id']}: {response.json()}")
        changed.append(record["example_id"])
    return sorted(changed)


def _append_provenance(
    data: Path,
    created: Sequence[tuple[str, str, int]],
    annotated_at: str,
    partition: str = "extension400",
) -> None:
    """Record who annotated every completed example, seeding legacy rows on first use."""
    path = data / PROVENANCE_FILE
    rows: list[dict[str, Any]] = []
    if not path.exists():
        for line in (data / "annotations.jsonl").read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record["example_id"] not in {example_id for example_id, _, _ in created}:
                rows.append(
                    {
                        "example_id": record["example_id"],
                        "post_revision_id": record["source"]["post_revision_id"],
                        "annotator": LEGACY_ANNOTATOR,
                        "partition": "pilot100",
                    }
                )
    rows += [
        {
            "example_id": example_id,
            "post_revision_id": revision_id,
            "annotator": ANNOTATOR,
            "partition": partition,
            "batch": batch_name,
            "method": "quote-anchored annotation validated by golden_v0_anchor",
            "annotated_at": annotated_at,
        }
        for example_id, batch_name, revision_id in created
    ]
    with path.open("a", encoding="utf-8") as stream:
        stream.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def main() -> int:
    """Run calibration scoring or import from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    calibration = commands.add_parser("calibration")
    calibration.add_argument("--batch", type=Path, default=WORK / "batches" / "calib01")
    importer = commands.add_parser("import")
    importer.add_argument("batches", nargs="+")
    importer.add_argument("--work", type=Path, default=WORK)
    importer.add_argument("--partition", default="extension400")
    args = parser.parse_args()
    if args.command == "calibration":
        report = calibration_report(args.batch, DATA / "annotations.jsonl")
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    renormalized = renormalize_imported(DATA)
    if renormalized:
        print(f"Re-resolved variant names in {', '.join(renormalized)}")
    created = import_batches(
        [args.work / "batches" / name for name in args.batches],
        DATA,
        datetime.now(UTC).isoformat(timespec="seconds"),
        args.partition,
    )
    print(f"Imported {len(created)} examples: {created[0]}..{created[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
