"""How many sampled stored posts pass the prefilter without vs with the migration-015 aliases.

Usage: volume.py POSTS_JSONL
"""

import json
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

sys.path[:0] = ["experiments/dspy/src", "packages/monitoring-common/src"]
from mamay_golden_v2 import load_seed_aliases  # noqa: E402
from monitoring_common.contracts import matched_registry_entity_ids  # noqa: E402

SEED = Path("infra/postgres/init/003_registry_seed.sql")
OLD = load_seed_aliases(SEED, None)
NEW = load_seed_aliases(SEED)


def match(text: str) -> tuple[set[int], set[int]]:
    return set(matched_registry_entity_ids(text, OLD)), set(matched_registry_entity_ids(text, NEW))


if __name__ == "__main__":
    posts = [
        json.loads(line)["text"] for line in open(sys.argv[1], encoding="utf-8") if line.strip()
    ]
    with Pool() as pool:
        results = pool.map(match, posts, chunksize=20)
    names = {row["entity_id"]: row["canonical_name"] for row in NEW}
    old_posts = sum(bool(a) for a, _ in results)
    new_posts = sum(bool(b) for _, b in results)
    old_pairs = sum(len(a) for a, _ in results)
    new_pairs = sum(len(b) for _, b in results)
    gained = Counter(names[e] for a, b in results for e in b - a)
    print(f"posts {len(posts)}: pass prefilter {old_posts} -> {new_posts}")
    print(f"post x entity candidates {old_pairs} -> {new_pairs}")
    print("most gained:", gained.most_common(20))
