"""Generate a DVC-tracked registry coverage snapshot from PostgreSQL.

Counts latest accessible posts with the production registry matching policy and records the
analysis queue throughput used to estimate the remaining processing time.
"""

import argparse
import asyncio
import csv
import json
import os
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
from monitoring_common.contracts.inference_v3 import _inflection_forms, _word_tokens

DEFAULT_OUTPUT = Path("experiments/dspy/data/registry_post_coverage")
OUTPUT_SCHEMA_VERSION = "registry_post_coverage_v1"
CSV_FIELDS = ("entity_id", "canonical_name", "coarse_type", "matched_post_count")
REPAIR_MIGRATION = "011_repair_inference_pass_attempts_unique.sql"


class PreparedRegistryMatcher:
    """Apply production registry matching efficiently across a historical post corpus.

    Args:
        aliases: Active registry aliases returned by PostgreSQL.
    """

    def __init__(self, aliases: Sequence[Mapping[str, Any]]) -> None:
        self._aliases_by_first_token: dict[str, list[tuple[int, tuple[frozenset[str], ...]]]] = {}
        surname_owners: dict[str, set[int]] = {}
        self._chesno_acronym_ids: set[int] = set()
        self._chesno_movement_ids: set[int] = set()
        for row in aliases:
            entity_id = int(row["entity_id"])
            alias = str(row["alias"])
            canonical_name = str(row["canonical_name"])
            normalized_alias = str(row["normalized_alias"])
            if canonical_name == "Рух ЧЕСНО" and normalized_alias == "чесно":
                self._chesno_acronym_ids.add(entity_id)
                continue
            if canonical_name == "Рух ЧЕСНО" and normalized_alias == "рух чесно":
                self._chesno_movement_ids.add(entity_id)
                continue
            tokens = _word_tokens(alias)
            if not tokens:
                continue
            token_forms = tuple(_inflection_forms(token) for token in tokens)
            for first_form in token_forms[0]:
                self._aliases_by_first_token.setdefault(first_form, []).append(
                    (entity_id, token_forms)
                )
            if str(row["coarse_type"]) == "person" and len(tokens) >= 2 and len(tokens[-1]) >= 4:
                surname_owners.setdefault(tokens[-1], set()).add(entity_id)
        self._unique_surnames_by_form: dict[str, set[int]] = {}
        for surname, owners in surname_owners.items():
            if len(owners) == 1:
                for form in _inflection_forms(surname):
                    self._unique_surnames_by_form.setdefault(form, set()).update(owners)

    def matched_entity_ids(self, source_text: str) -> list[int]:
        """Return entity IDs admitted by the production direct-alias policy.

        Args:
            source_text: One post revision's text.

        Returns:
            Sorted IDs of the monitored entities matched in the post.
        """
        source_tokens = _word_tokens(source_text)
        matched: set[int] = set()
        for start, source_token in enumerate(source_tokens):
            for entity_id, token_forms in self._aliases_by_first_token.get(source_token, []):
                if len(token_forms) > len(source_tokens) - start:
                    continue
                if all(
                    source_tokens[start + offset] in forms
                    for offset, forms in enumerate(token_forms[1:], start=1)
                ):
                    matched.add(entity_id)
            matched.update(self._unique_surnames_by_form.get(source_token, set()))
        if self._chesno_acronym_ids and re.search(r"(?<!\\w)ЧЕСНО(?!\\w)", source_text):
            matched.update(self._chesno_acronym_ids)
        if self._chesno_movement_ids and re.search(
            r'(?<!\\w)(?i:рух)\\s+[«"“]?ЧЕСНО[»"”]?(?!\\w)', source_text
        ):
            matched.update(self._chesno_movement_ids)
        return sorted(matched)


def coverage_records(
    posts: Iterable[str],
    entities: Sequence[Mapping[str, Any]],
    aliases: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    """Count posts admitted for every active registry entity.

    Args:
        posts: Texts of the latest accessible post revisions.
        entities: Active registry entities to include in the output.
        aliases: Approved aliases used by the production matcher.

    Returns:
        Per-entity records, number of scanned posts, and number matching any entity.
    """
    counts: Counter[int] = Counter()
    matcher = PreparedRegistryMatcher(aliases)
    total_posts = 0
    matched_posts = 0
    for content in posts:
        total_posts += 1
        matched_ids = matcher.matched_entity_ids(content)
        if matched_ids:
            matched_posts += 1
            counts.update(matched_ids)
    records = [
        {
            "entity_id": int(entity["id"]),
            "canonical_name": str(entity["canonical_name"]),
            "coarse_type": str(entity["coarse_type"]),
            "matched_post_count": counts[int(entity["id"])],
        }
        for entity in entities
        if bool(entity["monitored"])
    ]
    return (
        sorted(records, key=lambda record: (record["canonical_name"], record["entity_id"])),
        total_posts,
        matched_posts,
    )


def build_summary(
    *,
    generated_at: datetime,
    active_entities: int,
    approved_aliases: int,
    latest_posts_scanned: int,
    posts_matching_any_entity: int,
    queue_statuses: Mapping[str, int],
    completed_runs: int,
    first_started_at: datetime | None,
    last_completed_at: datetime | None,
    average_seconds_per_post: float | None,
    analysis_concurrency: int = 1,
) -> dict[str, Any]:
    """Build a serializable operational snapshot and queue ETA.

    The ETA is omitted until a nonzero average duration is available. It excludes idle periods,
    including operational maintenance windows, and assumes the configured number of worker slots.

    Args:
        generated_at: Snapshot creation time.
        active_entities: Number of monitored registry entities.
        approved_aliases: Number of aliases used for matching.
        latest_posts_scanned: Number of current post revisions examined.
        posts_matching_any_entity: Number of posts with at least one entity match.
        queue_statuses: Job count keyed by queue status.
        completed_runs: Successful runs since the repair migration.
        first_started_at: Start time of the first observed completed run.
        last_completed_at: Completion time of the last observed run.
        average_seconds_per_post: Mean duration of the observed completed runs.
        analysis_concurrency: Number of concurrently processing worker jobs.

    Returns:
        JSON-compatible coverage, queue, throughput, and ETA metadata.
    """
    del first_started_at, last_completed_at
    observed_jobs_per_second = (
        analysis_concurrency / average_seconds_per_post if average_seconds_per_post else None
    )
    remaining_jobs = queue_statuses.get("pending", 0) + queue_statuses.get("leased", 0)
    eta_seconds = remaining_jobs / observed_jobs_per_second if observed_jobs_per_second else None
    estimated_completion_at = (
        (generated_at + timedelta(seconds=eta_seconds)).isoformat()
        if eta_seconds is not None
        else None
    )
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "matching_policy": "production matched_registry_entity_ids on latest accessible revisions",
        "registry": {"active_entities": active_entities, "approved_aliases": approved_aliases},
        "posts": {
            "latest_accessible_revisions_scanned": latest_posts_scanned,
            "matching_any_monitored_entity": posts_matching_any_entity,
        },
        "analysis_queue": dict(sorted(queue_statuses.items())),
        "throughput_since_repair": {
            "migration": REPAIR_MIGRATION,
            "completed_runs": completed_runs,
            "analysis_concurrency": analysis_concurrency,
            "average_seconds_per_post": average_seconds_per_post,
            "observed_jobs_per_second": observed_jobs_per_second,
            "remaining_pending_or_leased_jobs": remaining_jobs,
            "estimated_remaining_seconds": eta_seconds,
            "estimated_completion_at": estimated_completion_at,
        },
    }


async def generate(dsn: str, output: Path) -> dict[str, Any]:
    """Generate the CSV and summary snapshot from a PostgreSQL read-only workload.

    Args:
        dsn: PostgreSQL connection string.
        output: Directory for the generated DVC-managed files.

    Returns:
        The generated summary metadata.
    """
    connection = await asyncpg.connect(dsn)
    try:
        entities = await connection.fetch(
            """SELECT id, canonical_name, coarse_type, monitored FROM registry_entities
               WHERE monitored ORDER BY canonical_name, id"""
        )
        aliases = await connection.fetch(
            """SELECT entity.id AS entity_id, entity.canonical_name, entity.coarse_type,
                      entity.monitored, alias.alias, alias.normalized_alias
               FROM registry_entities AS entity
               JOIN entity_aliases AS alias ON alias.entity_id = entity.id
               WHERE entity.monitored ORDER BY entity.id, alias.id"""
        )
        counts: Counter[int] = Counter()
        scanned_posts = 0
        matched_posts = 0
        matcher = PreparedRegistryMatcher(aliases)
        async with connection.transaction():
            async for row in connection.cursor(
                """SELECT DISTINCT ON (post.id) revision.content
                   FROM raw_posts AS post
                   JOIN post_revisions AS revision ON revision.raw_post_id = post.id
                   WHERE post.deleted_at IS NULL AND post.inaccessible_at IS NULL
                   ORDER BY post.id, revision.revision_number DESC""",
                prefetch=100,
            ):
                scanned_posts += 1
                matched_ids = matcher.matched_entity_ids(str(row["content"]))
                if matched_ids:
                    matched_posts += 1
                    counts.update(matched_ids)
        records = [
            {
                "entity_id": int(entity["id"]),
                "canonical_name": str(entity["canonical_name"]),
                "coarse_type": str(entity["coarse_type"]),
                "matched_post_count": counts[int(entity["id"])],
            }
            for entity in entities
        ]
        records.sort(key=lambda record: (record["canonical_name"], record["entity_id"]))
        queue_rows = await connection.fetch(
            "SELECT status, count(*) AS count FROM analysis_jobs GROUP BY status"
        )
        throughput = await connection.fetchrow(
            """WITH repair AS (
                   SELECT applied_at FROM schema_migrations WHERE version = $1
               ), runs AS (
                   SELECT run.created_at, run.completed_at
                   FROM analysis_runs AS run CROSS JOIN repair
                   WHERE run.status = 'completed' AND run.completed_at >= repair.applied_at
               )
               SELECT count(*) AS completed_runs, min(created_at) AS first_started_at,
                      max(completed_at) AS last_completed_at,
                      avg(extract(epoch FROM completed_at - created_at))
                          AS average_seconds_per_post
               FROM runs""",
            REPAIR_MIGRATION,
        )
    finally:
        await connection.close()
    summary = build_summary(
        generated_at=datetime.now(UTC),
        active_entities=len(entities),
        approved_aliases=len(aliases),
        latest_posts_scanned=scanned_posts,
        posts_matching_any_entity=matched_posts,
        queue_statuses={str(row["status"]): int(row["count"]) for row in queue_rows},
        completed_runs=int(throughput["completed_runs"]),
        first_started_at=throughput["first_started_at"],
        last_completed_at=throughput["last_completed_at"],
        average_seconds_per_post=(
            float(throughput["average_seconds_per_post"])
            if throughput["average_seconds_per_post"] is not None
            else None
        ),
        analysis_concurrency=int(os.environ.get("ANALYSIS_CONCURRENCY", "1")),
    )
    write_output(output, records, summary)
    return summary


def write_output(
    output: Path, records: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]
) -> None:
    """Write an inspectable coverage CSV and operational summary JSON.

    Args:
        output: Directory receiving the generated files.
        records: Per-entity coverage rows.
        summary: Snapshot metadata and throughput estimate.
    """
    output.mkdir(parents=True, exist_ok=True)
    with (output / "entity_post_counts.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def validate_output(output: Path) -> None:
    """Validate generated files before DVC versioning.

    Args:
        output: Directory containing the generated files.

    Raises:
        ValueError: If a required file, schema version, header, or entity row count is invalid.
    """
    with (output / "entity_post_counts.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CSV_FIELDS:
            raise ValueError("entity_post_counts.csv has an unexpected header")
        rows = list(reader)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    if summary.get("schema_version") != OUTPUT_SCHEMA_VERSION:
        raise ValueError("summary.json has an unexpected schema version")
    if len(rows) != summary.get("registry", {}).get("active_entities"):
        raise ValueError("CSV row count does not match the active registry entity count")
    identifiers = [row["entity_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("entity_post_counts.csv contains duplicate entity IDs")


def parse_args() -> argparse.Namespace:
    """Parse the generator command-line interface.

    Returns:
        Parsed output-path and validation-mode options.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Generate or validate the registry coverage artifact.

    Raises:
        SystemExit: If generation is requested without a PostgreSQL connection string.
    """
    args = parse_args()
    if args.validate_only:
        validate_output(args.output)
        return
    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        raise SystemExit("Set POSTGRES_DSN to generate registry coverage")
    summary = asyncio.run(generate(dsn, args.output))
    print(json.dumps(summary["throughput_since_repair"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
