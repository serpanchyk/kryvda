"""Select and prepare additional golden_v0 posts for quote-anchored annotation.

The selection reads PostgreSQL in a read-only transaction, keeps only posts admitted by the
production registry matcher, and favours the anti-corruption actors that dominate the reviewed
pilot while retaining general posts. Outputs go to an ignored work directory that is versioned
with DVC once annotation finishes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from golden_v0_anchor import ANNOTATIONS_PATH, SOURCE_FIELDS, to_anchor
from golden_v0_validation import DATASET_DIRECTORY

REPOSITORY = DATASET_DIRECTORY.parents[2]
DATA = DATASET_DIRECTORY / "data"
WORK = DATASET_DIRECTORY / "extension" / "work"
SEED = 20261010
MIN_LENGTH, MAX_LENGTH = 120, 3500
CORE_SHARE = 0.65
PER_ENTITY_CAP = 0.08
BATCH_SIZE = 10
FEWSHOT_IDS = ("golden_v0-001", "golden_v0-041", "golden_v0-124")
# Blind re-annotation of reviewed diagnostic45 posts measures agreement with the pilot.
CALIBRATION_IDS = (
    "golden_v0-176",
    "golden_v0-146",
    "golden_v0-190",
    "golden_v0-246",
    "golden_v0-137",
    "golden_v0-138",
    "golden_v0-219",
    "golden_v0-143",
    "golden_v0-187",
    "golden_v0-245",
)
# Broad state actors appear in most war news; they do not mark a post as core monitoring scope.
GENERIC_ENTITIES = frozenset(
    {
        "Володимир Зеленський",
        "Збройні Сили України",
        "Служба безпеки України",
        "Офіс Президента України",
        "Кабінет Міністрів України",
        "Росія",
        "Російська Федерація",
        "Міністерство закордонних справ України",
        "Генеральний штаб Збройних Сил України",
        "Національна поліція України",
        "Головне управління розвідки Міністерства оборони України",
        "Міністерство оборони України",
        "Верховна Рада України",
        "Збройні сили Російської Федерації",
    }
)


def normalized_text(text: str) -> str:
    """Return a duplicate-detection key that ignores punctuation, case, and emoji."""
    return re.sub(r"\W+", " ", text.casefold()).strip()[:300]


def core_entities(records: Iterable[Mapping[str, Any]]) -> set[str]:
    """Return canonical names annotated in the reviewed pilot, excluding broad state actors."""
    names = {
        entity["canonical_name"]
        for record in records
        for entity in record["annotations"]["entities"]
        if entity["canonical_name"]
    }
    return names - GENERIC_ENTITIES


def select_posts(
    rows: Iterable[Mapping[str, Any]],
    match: Callable[[str], list[str]],
    core: set[str],
    excluded_posts: set[int],
    excluded_texts: set[str],
    target: int,
    seed: int = SEED,
) -> list[dict[str, Any]]:
    """Choose a reproducible, channel-stratified sample of registry-matched posts.

    Channels receive square-root-proportional quotas so small channels stay represented. Within
    each channel ``CORE_SHARE`` of the quota comes from posts matching a core entity, and no
    entity may appear in more than ``PER_ENTITY_CAP`` of the sample.

    Args:
        rows: Latest accessible post revisions with source fields.
        match: Returns canonical names of registry entities matched in a text.
        core: Canonical names that mark core monitoring scope.
        excluded_posts: Raw post IDs already present in the editor.
        excluded_texts: Normalized texts already present in the editor.
        target: Number of posts to select.
        seed: Random seed.

    Returns:
        Selected posts with ``matched_entities`` and ``core`` metadata.
    """
    seen = set(excluded_texts)
    pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        text = row["text"] or ""
        if row["raw_post_id"] in excluded_posts or not MIN_LENGTH <= len(text) <= MAX_LENGTH:
            continue
        key = normalized_text(text)
        if key in seen:
            continue
        matched = match(text)
        if not matched:
            continue
        seen.add(key)
        post = {field: row[field] for field in SOURCE_FIELDS}
        post["matched_entities"] = matched
        post["core"] = bool(core.intersection(matched))
        pool[str(row["channel_reference"])].append(post)
    generator = random.Random(seed)
    for channel in sorted(pool):
        generator.shuffle(pool[channel])
    weights = {channel: len(posts) ** 0.5 for channel, posts in pool.items()}
    total_weight = sum(weights.values())
    cap = max(3, int(target * PER_ENTITY_CAP))
    counts: Counter[str] = Counter()
    chosen: list[dict[str, Any]] = []
    for channel in sorted(pool):
        quota = max(1, round(target * weights[channel] / total_weight))
        core_quota = round(quota * CORE_SHARE)
        core_posts = [post for post in pool[channel] if post["core"]]
        general_posts = [post for post in pool[channel] if not post["core"]]
        taken = 0
        for group, limit in ((core_posts, core_quota), (general_posts, quota)):
            for post in group:
                if taken >= limit:
                    break
                if any(counts[name] >= cap for name in post["matched_entities"]):
                    continue
                counts.update(post["matched_entities"])
                chosen.append(post)
                taken += 1
    generator.shuffle(chosen)
    return chosen[:target]


def registry_reference(local: Sequence[Mapping[str, Any]], production: Sequence[Any]) -> str:
    """Render both registries as a greppable reference for annotators."""
    lines = [
        "# Local golden registry (reuse canonical_name + entity_type EXACTLY when it matches)",
        "",
    ]
    lines += [
        f"- {entry['canonical_name']} | {entry['entity_type']} | aliases: "
        + ", ".join(entry["aliases"][:6])
        for entry in local
    ]
    lines += ["", "# Production monitored registry (preferred spelling for other actors)", ""]
    lines += [
        f"- {row['canonical_name']} | {row['coarse_type']} | aliases: "
        + ", ".join(alias for alias in row["aliases"][:6] if alias)
        for row in production
    ]
    return "\n".join(lines) + "\n"


def fewshot_reference(records: Mapping[str, Mapping[str, Any]]) -> str:
    """Render the reviewed few-shot examples in the anchor format."""
    parts = []
    for example_id in FEWSHOT_IDS:
        record = records[example_id]
        anchor = json.dumps(to_anchor(dict(record)), ensure_ascii=False, indent=1)
        parts.append(
            f"## Example {example_id}\n\nPOST TEXT:\n```\n{record['source']['text']}\n```\n\n"
            f"ANNOTATION:\n```json\n{anchor}\n```\n"
        )
    return "\n".join(parts)


def write_batches(posts: Sequence[Mapping[str, Any]], directory: Path, prefix: str) -> None:
    """Split posts into numbered batch directories with an empty ``out`` folder."""
    for index in range(0, len(posts), BATCH_SIZE):
        batch = directory / f"{prefix}{index // BATCH_SIZE + 1:02d}"
        (batch / "out").mkdir(parents=True, exist_ok=True)
        content = [{field: post[field] for field in SOURCE_FIELDS} for post in posts[index:]]
        (batch / "posts.json").write_text(
            json.dumps(content[:BATCH_SIZE], ensure_ascii=False, indent=1), encoding="utf-8"
        )


def database_dsn() -> str:
    """Build a host-side DSN from the repository ``.env`` file."""
    values: dict[str, str] = {}
    for line in (REPOSITORY / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return (
        f"postgresql://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}@localhost:"
        f"{values.get('POSTGRES_PORT', '5433')}/{values['POSTGRES_DB']}"
    )


async def fetch_corpus(dsn: str) -> tuple[list[Any], list[Any], list[Any]]:
    """Read aliases, monitored entities, and latest accessible revisions read-only."""
    import asyncpg

    connection = await asyncpg.connect(dsn)
    try:
        async with connection.transaction(readonly=True):
            aliases = await connection.fetch(
                """SELECT entity.id AS entity_id, entity.canonical_name, entity.coarse_type,
                          alias.alias, alias.normalized_alias
                   FROM registry_entities AS entity
                   JOIN entity_aliases AS alias ON alias.entity_id = entity.id
                   WHERE entity.monitored ORDER BY entity.id, alias.id"""
            )
            entities = await connection.fetch(
                """SELECT entity.canonical_name, entity.coarse_type,
                          array_agg(alias.alias ORDER BY alias.id) AS aliases
                   FROM registry_entities AS entity
                   LEFT JOIN entity_aliases AS alias ON alias.entity_id = entity.id
                   WHERE entity.monitored GROUP BY 1, 2 ORDER BY 1"""
            )
            rows = await connection.fetch(
                """SELECT DISTINCT ON (post.id) revision.id AS post_revision_id,
                          post.id AS raw_post_id, post.channel_id,
                          channel.configured_reference AS channel_reference,
                          post.telegram_message_id, post.published_at,
                          revision.content AS text
                   FROM raw_posts AS post
                   JOIN post_revisions AS revision ON revision.raw_post_id = post.id
                   JOIN monitored_channels AS channel ON channel.id = post.channel_id
                   WHERE post.deleted_at IS NULL AND post.inaccessible_at IS NULL
                   ORDER BY post.id, revision.revision_number DESC"""
            )
    finally:
        await connection.close()
    return aliases, entities, rows


def prepare(target: int, work: Path) -> dict[str, Any]:
    """Select posts and write the selection, references, and batches into ``work``."""
    sys.path.insert(0, str(REPOSITORY / "experiments/dspy/src"))
    from registry_post_coverage import PreparedRegistryMatcher

    aliases, entities, rows = asyncio.run(fetch_corpus(database_dsn()))
    names = {int(row["entity_id"]): str(row["canonical_name"]) for row in aliases}
    matcher = PreparedRegistryMatcher(aliases)
    state = json.loads((DATA / "editor.json").read_text(encoding="utf-8"))
    sources = [item["record"]["source"] for item in state["records"].values()]
    records = {
        record["example_id"]: record
        for record in map(json.loads, ANNOTATIONS_PATH.read_text(encoding="utf-8").splitlines())
    }
    posts = select_posts(
        ({**dict(row), "published_at": row["published_at"].isoformat()} for row in rows),
        lambda text: [names[entity_id] for entity_id in matcher.matched_entity_ids(text)],
        core_entities(records.values()),
        {int(source["raw_post_id"]) for source in sources},
        {normalized_text(source["text"]) for source in sources},
        target,
    )
    work.mkdir(parents=True, exist_ok=True)
    (work / "selection.jsonl").write_text(
        "".join(json.dumps(post, ensure_ascii=False) + "\n" for post in posts), encoding="utf-8"
    )
    local = [
        json.loads(line)
        for line in (DATA / "entity_registry.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (work / "registry.md").write_text(registry_reference(local, entities), encoding="utf-8")
    (work / "fewshot.md").write_text(fewshot_reference(records), encoding="utf-8")
    write_batches(posts, work / "batches", "b")
    write_batches(
        [records[example_id]["source"] for example_id in CALIBRATION_IDS],
        work / "batches",
        "calib",
    )
    return {
        "selected": len(posts),
        "core": sum(post["core"] for post in posts),
        "channels": Counter(post["channel_reference"] for post in posts),
    }


def main() -> int:
    """Run selection from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=400)
    parser.add_argument("--work", type=Path, default=WORK)
    args = parser.parse_args()
    print(prepare(args.target, args.work))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
