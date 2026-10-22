"""Annotate which registry organizations a golden_v0 post links each criticised person to.

Convention (2026-10-23): criticism of a person is criticism of an organization when the post
itself presents the person as its head, member, employee or former employee. ``export`` writes
every post with a negatively evaluated person and a monitored registry organization in its
text; reviewers answer in ``out.json`` next to each ``items.json``; ``collect`` writes
``data/affiliations.jsonl``, which the post x entity stance report applies to the gold.

Examples:
    uv run python experiments/datasets/golden_v0/src/golden_v0_affiliations.py export
    uv run python experiments/datasets/golden_v0/src/golden_v0_affiliations.py collect
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from golden_v0_extension import DATA, REPOSITORY

for _source in ("experiments/dspy/src", "packages/monitoring-common/src"):
    if str(REPOSITORY / _source) not in sys.path:
        sys.path.append(str(REPOSITORY / _source))

from mamay_golden_v2 import load_seed_aliases  # noqa: E402
from monitoring_common.contracts import matched_registry_entity_ids  # noqa: E402

WORK = REPOSITORY / "experiments/datasets/golden_v0/extension/affiliation_work"
SEED = REPOSITORY / "infra/postgres/init/003_registry_seed.sql"
OUTPUT = "affiliations.jsonl"


def review_post(
    record: Mapping[str, Any], aliases: Sequence[Mapping[str, Any]]
) -> dict[str, Any] | None:
    """Return the people and organizations to link in one post, or ``None`` if nothing to do."""
    text = record["source"]["text"]
    annotations = record["annotations"]
    negative = {s["entity_id"] for s in annotations["stances"] if s["value"] == "negative"}
    people = [
        {"entity_id": e["id"], "name": e.get("canonical_name") or e["surface_form"]}
        for e in annotations["entities"]
        if e["entity_type"] == "person" and e["id"] in negative
    ]
    kinds = {int(row["entity_id"]): row for row in aliases}
    organizations = [
        kinds[entity_id]["canonical_name"]
        for entity_id in matched_registry_entity_ids(text, aliases)
        if kinds[entity_id]["coarse_type"] != "person"
    ]
    if not people or not organizations:
        return None
    return {
        "example_id": record["example_id"],
        "text": text,
        "people": people,
        "organizations": organizations,
    }


def export(records: Sequence[Mapping[str, Any]], work: Path, batches: int) -> list[int]:
    """Write review batches of posts; returns the number of people per batch."""
    aliases = load_seed_aliases(SEED)
    posts = [post for record in records if (post := review_post(record, aliases))]
    size = -(-len(posts) // batches)
    counts = []
    for number in range(batches):
        group = posts[number * size : (number + 1) * size]
        if not group:
            continue
        directory = work / "batches" / f"a{number + 1:02}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "items.json").write_text(
            json.dumps(group, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        counts.append(sum(len(post["people"]) for post in group))
    return counts


def collect(work: Path, data: Path) -> int:
    """Check every answer and write the affiliations file; returns the number of links."""
    rows = []
    for directory in sorted((work / "batches").iterdir()):
        posts = json.loads((directory / "items.json").read_text(encoding="utf-8"))
        answers = json.loads((directory / "out.json").read_text(encoding="utf-8"))
        for post in posts:
            answer = answers.get(post["example_id"])
            if answer is None:
                raise ValueError(f"{directory.name}: missing {post['example_id']}")
            for person in post["people"]:
                decision = answer.get(person["entity_id"])
                if decision is None:
                    raise ValueError(f"{post['example_id']}: missing {person['entity_id']}")
                unknown = set(decision["organizations"]) - set(post["organizations"])
                if unknown:
                    raise ValueError(f"{post['example_id']}: unknown organizations {unknown}")
                if decision["organizations"]:
                    rows.append(
                        {
                            "example_id": post["example_id"],
                            "entity_id": person["entity_id"],
                            "person": person["name"],
                            "organizations": decision["organizations"],
                            "reason": decision.get("reason", ""),
                        }
                    )
    (data / OUTPUT).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    return len(rows)


def main(arguments: Sequence[str] | None = None) -> int:
    """Export review batches or collect the reviewed affiliations."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    exporter = commands.add_parser("export")
    exporter.add_argument("--batches", type=int, default=4)
    for command in (exporter, commands.add_parser("collect")):
        command.add_argument("--work", type=Path, default=WORK)
        command.add_argument("--data", type=Path, default=DATA)
    args = parser.parse_args(arguments)
    if args.command == "export":
        lines = (args.data / "annotations.jsonl").read_text(encoding="utf-8").splitlines()
        sizes = export([json.loads(line) for line in lines], args.work, args.batches)
        sys.stdout.write(f"Exported {sum(sizes)} people: {sizes}\n")
        return 0
    sys.stdout.write(f"Collected {collect(args.work, args.data)} person links\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
