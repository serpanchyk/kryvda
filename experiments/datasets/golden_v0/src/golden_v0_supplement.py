"""Annotate registry entities that the v2 aliases find in golden_v0 posts but the gold omits.

Registry aliases v2 admit actors (police, the army, the Rada) that annotators had skipped as
background, so any stance the pipeline gives them counted as a false positive. ``export`` lists,
per post, every registry entity the prefilter now matches without a gold record; reviewers
answer in ``out.json`` whether the post really refers to it and which stances it carries, under
the current conventions; ``collect`` writes ``data/supplement_stances.jsonl``, which the post x
entity stance report merges into the gold.

Examples:
    uv run python experiments/datasets/golden_v0/src/golden_v0_supplement.py export
    uv run python experiments/datasets/golden_v0/src/golden_v0_supplement.py collect
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from multiprocessing import Pool
from pathlib import Path
from typing import Any

from golden_v0_extension import DATA, REPOSITORY

for _source in ("experiments/dspy/src", "packages/monitoring-common/src"):
    if str(REPOSITORY / _source) not in sys.path:
        sys.path.append(str(REPOSITORY / _source))

from entity_stance_report import normalize_name, registry_names  # noqa: E402
from mamay_golden_v2 import load_seed_aliases  # noqa: E402
from monitoring_common.contracts import matched_registry_entity_ids  # noqa: E402

WORK = REPOSITORY / "experiments/datasets/golden_v0/extension/supplement_work"
SEED = REPOSITORY / "infra/postgres/init/003_registry_seed.sql"
OUTPUT = "supplement_stances.jsonl"
ALIASES = load_seed_aliases(SEED)
NAMES = registry_names(ALIASES)
CANONICAL = {int(row["entity_id"]): str(row["canonical_name"]) for row in ALIASES}


def missing_entities(record: Mapping[str, Any]) -> list[str]:
    """Return registry entities matched in the post text that have no gold entity."""
    annotated = {
        NAMES.get(normalize_name(entity.get("canonical_name") or ""))
        for entity in record["annotations"]["entities"]
    }
    matched = matched_registry_entity_ids(record["source"]["text"], ALIASES)
    return [CANONICAL[i] for i in matched if CANONICAL[i] not in annotated]


def export(records: Sequence[Mapping[str, Any]], work: Path, batches: int) -> list[int]:
    """Write review batches; returns the number of entities per batch."""
    with Pool() as pool:
        missing = pool.map(missing_entities, records, chunksize=10)
    posts = [
        {"example_id": r["example_id"], "text": r["source"]["text"], "entities": m}
        for r, m in zip(records, missing, strict=True)
        if m
    ]
    size = -(-len(posts) // batches)
    counts = []
    for number in range(batches):
        group = posts[number * size : (number + 1) * size]
        if not group:
            continue
        directory = work / "batches" / f"s{number + 1:02}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "items.json").write_text(
            json.dumps(group, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        counts.append(sum(len(post["entities"]) for post in group))
    return counts


def collect(work: Path, data: Path) -> int:
    """Check every answer and write the supplement; returns the number of referenced entities."""
    rows = []
    for directory in sorted((work / "batches").iterdir()):
        posts = json.loads((directory / "items.json").read_text(encoding="utf-8"))
        answers = json.loads((directory / "out.json").read_text(encoding="utf-8"))
        for post in posts:
            for entity in post["entities"]:
                answer = answers.get(post["example_id"], {}).get(entity)
                if answer is None:
                    raise ValueError(f"{post['example_id']}: missing {entity}")
                if not answer["referenced"]:
                    continue
                stances = [
                    stance
                    for stance, key in (("негативне", "negative"), ("позитивне", "positive"))
                    if answer[key]
                ]
                rows.append(
                    {
                        "example_id": post["example_id"],
                        "entity": entity,
                        "stances": stances or ["відсутнє"],
                        "reason": answer.get("reason", ""),
                    }
                )
    (data / OUTPUT).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    return len(rows)


def main(arguments: Sequence[str] | None = None) -> int:
    """Export review batches or collect the reviewed supplement."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    exporter = commands.add_parser("export")
    exporter.add_argument("--batches", type=int, default=6)
    for command in (exporter, commands.add_parser("collect")):
        command.add_argument("--work", type=Path, default=WORK)
        command.add_argument("--data", type=Path, default=DATA)
    args = parser.parse_args(arguments)
    if args.command == "export":
        lines = (args.data / "annotations.jsonl").read_text(encoding="utf-8").splitlines()
        sizes = export([json.loads(line) for line in lines], args.work, args.batches)
        sys.stdout.write(f"Exported {sum(sizes)} entities: {sizes}\n")
        return 0
    sys.stdout.write(f"Collected {collect(args.work, args.data)} referenced entities\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
