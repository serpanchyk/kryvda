"""Measure-only: aggregate alias recall on the golden test split; prints counts only."""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path[:0] = ["experiments/dspy/src", "packages/monitoring-common/src"]
from entity_stance_report import DEFAULT_ANNOTATIONS, normalize_name, registry_names  # noqa: E402
from golden_report import heldout_example_ids  # noqa: E402
from mamay_golden_v2 import load_seed_aliases  # noqa: E402
from monitoring_common.contracts import alias_occurs  # noqa: E402

test = heldout_example_ids(DEFAULT_ANNOTATIONS)
for seed in sys.argv[1:]:
    aliases = load_seed_aliases(Path(seed))
    names = registry_names(aliases)
    by_name = defaultdict(list)
    for row in aliases:
        by_name[row["canonical_name"]].append(row)
    total = hit = 0
    for line in open(DEFAULT_ANNOTATIONS, encoding="utf-8"):
        record = json.loads(line)
        if record["example_id"] not in test:
            continue
        text = record["source"]["text"]
        for entity in record["annotations"]["entities"]:
            name = names.get(normalize_name(entity.get("canonical_name") or ""))
            if not name:
                continue
            span = entity["mention_span"]
            total += 1
            hit += any(
                alias_occurs(text[span["start"] : span["end"]], r["alias"]) for r in by_name[name]
            )
    print(Path(seed).name, f"test mentions {total}, matched {hit} ({hit / total:.1%})")
