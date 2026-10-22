"""Dev-only: which golden mentions of registry entities the alias prefilter misses.

Usage: alias_recall.py SEED_SQL [MISSED_JSON]
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path[:0] = ["experiments/dspy/src", "packages/monitoring-common/src"]
from entity_stance_report import DEFAULT_ANNOTATIONS, normalize_name, registry_names  # noqa: E402
from golden_report import heldout_example_ids  # noqa: E402
from mamay_golden_v2 import load_seed_aliases  # noqa: E402
from monitoring_common.contracts import alias_occurs  # noqa: E402

aliases = load_seed_aliases(Path(sys.argv[1]))
names = registry_names(aliases)
by_name = defaultdict(list)
for row in aliases:
    by_name[row["canonical_name"]].append(row)
test = heldout_example_ids(DEFAULT_ANNOTATIONS)
missed = Counter()
total = hit = 0
for line in open(DEFAULT_ANNOTATIONS, encoding="utf-8"):
    record = json.loads(line)
    if record["example_id"] in test:
        continue
    text = record["source"]["text"]
    for entity in record["annotations"]["entities"]:
        name = names.get(normalize_name(entity.get("canonical_name") or ""))
        if not name:
            continue
        form = text[entity["mention_span"]["start"] : entity["mention_span"]["end"]]
        total += 1
        if any(alias_occurs(form, row["alias"]) for row in by_name[name]):
            hit += 1
        else:
            missed[(name, form)] += 1
print(f"dev gold mentions of registry entities: {total}, matched: {hit} ({hit / total:.1%})")
if len(sys.argv) > 2:
    rows = sorted(([k[0], k[1], v] for k, v in missed.items()), key=lambda r: -r[2])
    Path(sys.argv[2]).write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
