"""Count sampled posts matched by each new alias, to find aliases that catch ordinary words.

Usage: alias_hits.py POSTS_JSONL
"""

import json
import sys
from multiprocessing import Pool
from pathlib import Path

sys.path[:0] = ["packages/monitoring-common/src"]
from monitoring_common.contracts import alias_occurs  # noqa: E402

WORK = Path("experiments/registry_aliases/work")
PROPOSALS = [
    (name, item["alias"], item["ambiguity"])
    for k in range(1, 5)
    for name, items in json.loads((WORK / f"out{k}.json").read_text(encoding="utf-8")).items()
    for item in items
]
POSTS = [json.loads(line)["text"] for line in open(sys.argv[1], encoding="utf-8") if line.strip()]


def count(proposal: tuple[str, str, str]) -> tuple[str, str, str, int]:
    name, alias, level = proposal
    return name, alias, level, sum(alias_occurs(text, alias) for text in POSTS)


if __name__ == "__main__":
    with Pool() as pool:
        rows = sorted(pool.map(count, PROPOSALS, chunksize=8), key=lambda r: -r[3])
    (WORK / "alias_hits.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8"
    )
    for name, alias, level, hits in rows[:45]:
        print(f"{hits:5} {level:6} {alias!r:28} -> {name}")
