"""Merge reviewed alias proposals into a seed copy; ambiguity levels listed in EXCLUDE are dropped.

Usage: merge.py OUT_SEED [--max-ambiguity low|medium|high]
"""

import json
import sys
from collections import Counter
from pathlib import Path

WORK = Path("experiments/registry_aliases/work")
LEVELS = ["low", "medium", "high"]
limit = sys.argv[sys.argv.index("--max-ambiguity") + 1] if "--max-ambiguity" in sys.argv else "high"
allowed = LEVELS[: LEVELS.index(limit) + 1]
proposals: dict[str, list[dict]] = {}
for k in range(1, 5):
    proposals.update(json.loads((WORK / f"out{k}.json").read_text(encoding="utf-8")))
content = Path("infra/postgres/init/003_registry_seed.sql").read_text(encoding="utf-8")
head, rest = content.split("FROM stdin;\n", 1)
copy, tail = rest.split("\n\\.\n", 1)
lines, added = [], Counter()
for line in copy.splitlines():
    name, kind, raw = line.split("\t")
    current = [a.strip() for a in raw.split(";") if a.strip()]
    seen = {" ".join(a.casefold().split()) for a in [name, *current]}
    new = []
    for proposal in proposals.get(name, []):
        key = " ".join(proposal["alias"].casefold().split())
        if proposal["ambiguity"] in allowed and key not in seen and ";" not in key:
            seen.add(key)
            new.append(proposal["alias"].strip())
            added[proposal["ambiguity"]] += 1
    lines.append("\t".join([name, kind, "; ".join(current + new)]))
Path(sys.argv[1]).write_text(
    head + "FROM stdin;\n" + "\n".join(lines) + "\n\\.\n" + tail, encoding="utf-8"
)
print("entities", len(proposals), "added", dict(added))
