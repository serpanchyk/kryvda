"""Re-review neutral golden_v0 stance records under the positive-context convention (v2).

Convention v2 (2026-10-21): a source that presents an entity in a positive context is
``positive`` even without explicit praise: its successes and results, high trust or ratings,
the entity's own announcement of its successes, and routine actions the post frames favourably.
Only a flat, informational mention stays ``neutral``. Earlier extension and test annotations
put all of these in ``neutral``, so every neutral stance record is re-reviewed; negative and
positive records are left as they are.

``export`` writes the neutral records with their post and overlapping claims into review
batches; reviewers write ``out.json`` next to each ``items.json``. ``apply`` saves the decisions
through the annotation editor's own record endpoint (the editor service must be stopped) and
appends every change to ``data/stance_relabel_log.jsonl``.

Examples:
    uv run python experiments/datasets/golden_v0/src/golden_v0_stance_relabel.py export
    uv run python experiments/datasets/golden_v0/src/golden_v0_stance_relabel.py apply
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from golden_v0_extension import DATA, REPOSITORY

if str(REPOSITORY / "experiments/annotation-ui/src") not in sys.path:
    sys.path.append(str(REPOSITORY / "experiments/annotation-ui/src"))

WORK = REPOSITORY / "experiments/datasets/golden_v0/extension/relabel_work"
LOG_FILE = "stance_relabel_log.jsonl"
CONVENTION = "positive_context_v2"
DECISIONS = ("positive", "neutral")


def _overlaps(left: Sequence[Mapping[str, int]], right: Sequence[Mapping[str, int]]) -> bool:
    return any(a["start"] < b["end"] and b["start"] < a["end"] for a in left for b in right)


def review_items(record: Mapping[str, Any], self_only: bool = False) -> list[dict[str, Any]]:
    """Return one review item per neutral stance record of an annotated example.

    ``self_only`` keeps only self-presentation: records whose perspective is the entity itself.
    """
    text = record["source"]["text"]
    annotations = record["annotations"]
    entities = {entity["id"]: entity for entity in annotations["entities"]}

    def name(entity_id: str | None) -> str | None:
        entity = entities.get(entity_id or "")
        if entity is None:
            return None
        return str(entity.get("canonical_name") or entity["surface_form"])

    items = []
    for index, stance in enumerate(annotations["stances"]):
        perspective = stance["perspective"]
        if stance["value"] != "neutral" or (
            self_only and perspective.get("source_entity_id") != stance["entity_id"]
        ):
            continue
        spans = stance["evidence_spans"]
        items.append(
            {
                "item_id": f"{record['example_id']}:s{index}",
                "entity": name(stance["entity_id"]),
                "perspective": perspective["source_kind"],
                "perspective_entity": name(perspective.get("source_entity_id")),
                "evidence": [text[span["start"] : span["end"]] for span in spans],
                "claims": [
                    claim["normalized_text"]
                    for claim in annotations["claims"]
                    if stance["entity_id"] in claim["entity_ids"]
                    and _overlaps(claim["evidence_spans"], spans)
                ],
            }
        )
    return items


def export(
    records: Sequence[Mapping[str, Any]], work: Path, batches: int, self_only: bool = False
) -> list[int]:
    """Write review batches of whole posts with roughly equal item counts.

    Returns:
        Number of review items in every batch.
    """
    posts = [
        {"example_id": record["example_id"], "text": record["source"]["text"], "items": items}
        for record in records
        if (items := review_items(record, self_only))
    ]
    target = sum(len(post["items"]) for post in posts) / batches
    groups: list[list[dict[str, Any]]] = [[]]
    for post in posts:
        if len(groups) < batches and sum(len(p["items"]) for p in groups[-1]) >= target:
            groups.append([])
        groups[-1].append(post)
    for number, group in enumerate(groups, start=1):
        directory = work / "batches" / f"r{number:02}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "items.json").write_text(
            json.dumps(group, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    return [sum(len(post["items"]) for post in group) for group in groups]


def load_decisions(work: Path) -> dict[str, dict[str, str]]:
    """Read and check the reviewers' decisions for every exported item."""
    decisions: dict[str, dict[str, str]] = {}
    for directory in sorted((work / "batches").iterdir()):
        expected = {
            item["item_id"]
            for post in json.loads((directory / "items.json").read_text(encoding="utf-8"))
            for item in post["items"]
        }
        answers = json.loads((directory / "out.json").read_text(encoding="utf-8"))
        if set(answers) != expected:
            missing, extra = expected - set(answers), set(answers) - expected
            raise ValueError(
                f"{directory.name}: missing {sorted(missing)}, unknown {sorted(extra)}"
            )
        for item_id, answer in answers.items():
            if answer.get("value") not in DECISIONS:
                raise ValueError(f"{item_id}: value must be one of {DECISIONS}")
            decisions[item_id] = {"value": answer["value"], "reason": str(answer.get("reason", ""))}
    return decisions


def apply(
    data: Path,
    decisions: Mapping[str, Mapping[str, str]],
    changed_at: str,
    convention: str = CONVENTION,
) -> int:
    """Save positive decisions through the editor and log them; reruns are idempotent.

    Returns:
        Number of stance records relabelled, including ones an interrupted run saved.
    """
    from annotation_app import create_app
    from fastapi.testclient import TestClient

    state = json.loads((data / "editor.json").read_text(encoding="utf-8"))
    client = TestClient(create_app(data))
    log = []
    for key, item in state["records"].items():
        record = item["record"]
        changed = False
        for index, stance in enumerate(record["annotations"]["stances"]):
            item_id = f"{record['example_id']}:s{index}"
            decision = decisions.get(item_id)
            if decision is None or decision["value"] != "positive":
                continue
            # A rerun after an interrupted apply finds some decisions already saved.
            if stance["value"] not in ("neutral", "positive"):
                raise ValueError(f"{item_id} is no longer neutral")
            changed = changed or stance["value"] == "neutral"
            stance["value"] = "positive"
            log.append(
                {
                    "item_id": item_id,
                    "from": "neutral",
                    "to": "positive",
                    "reason": decision["reason"],
                    "convention": convention,
                    "changed_at": changed_at,
                }
            )
        if not changed:
            continue
        response = client.put(
            f"/api/records/{key}",
            json={"record": record, "status": item["status"], "version": item["version"]},
        )
        if response.status_code != 200:
            raise ValueError(f"{record['example_id']}: {response.json()}")
    with (data / LOG_FILE).open("a", encoding="utf-8") as stream:
        stream.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in log)
    return len(log)


def main(arguments: Sequence[str] | None = None) -> int:
    """Export review batches or apply the reviewed decisions."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    exporter = commands.add_parser("export")
    exporter.add_argument("--batches", type=int, default=8)
    exporter.add_argument("--self-only", action="store_true", help="only self-presentation")
    applier = commands.add_parser("apply")
    applier.add_argument("--convention", default=CONVENTION)
    for command in (exporter, applier):
        command.add_argument("--work", type=Path, default=WORK)
        command.add_argument("--data", type=Path, default=DATA)
    args = parser.parse_args(arguments)
    if args.command == "export":
        records = [
            json.loads(line)
            for line in (args.data / "annotations.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        sizes = export(records, args.work, args.batches, args.self_only)
        sys.stdout.write(f"Exported {sum(sizes)} neutral stance records: {sizes}\n")
        return 0
    changed = apply(
        args.data,
        load_decisions(args.work),
        datetime.now(UTC).isoformat(timespec="seconds"),
        args.convention,
    )
    sys.stdout.write(f"Relabelled {changed} stance records neutral -> positive\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
