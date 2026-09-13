"""Registry, candidate review, and deterministic backfill persistence."""

from collections.abc import Sequence
from typing import Any

import asyncpg
from monitoring_common.contracts import matched_registry_entity_ids, normalize_match_text


class RegistryRepository:
    """Own registry mutations and their historical analysis handoff."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_entities(self, monitored: bool | None = None) -> list[dict[str, Any]]:
        """Return registry entities with approved aliases."""
        rows = await self._pool.fetch(
            """SELECT entity.id, entity.canonical_name, entity.coarse_type, entity.monitored,
                      COALESCE(array_agg(alias.alias ORDER BY alias.id)
                      FILTER (WHERE alias.id IS NOT NULL), '{}') AS aliases
               FROM registry_entities AS entity
               LEFT JOIN entity_aliases AS alias ON alias.entity_id = entity.id
               WHERE ($1::boolean IS NULL OR entity.monitored = $1)
               GROUP BY entity.id ORDER BY entity.canonical_name""",
            monitored,
        )
        return [dict(row) for row in rows]

    async def create_entity(
        self,
        canonical_name: str,
        coarse_type: str,
        aliases: Sequence[str],
        monitored: bool,
        trigger_kind: str = "entity_created",
    ) -> tuple[int, int]:
        """Create a registry entity, approved aliases, and matching historical jobs."""
        unique_aliases = _unique_aliases(canonical_name, aliases)
        async with self._pool.acquire() as connection, connection.transaction():
            entity_id = int(
                await connection.fetchval(
                    """INSERT INTO registry_entities (canonical_name, coarse_type, monitored)
                       VALUES ($1, $2, $3) RETURNING id""",
                    canonical_name,
                    coarse_type,
                    monitored,
                )
            )
            await self._insert_aliases(connection, entity_id, unique_aliases)
            jobs = (
                await self._enqueue_backfill(connection, entity_id, trigger_kind)
                if monitored
                else 0
            )
        return entity_id, jobs

    async def update_entity(
        self,
        entity_id: int,
        canonical_name: str | None,
        coarse_type: str | None,
        monitored: bool | None,
    ) -> int | None:
        """Update entity metadata and backfill when monitoring becomes active."""
        async with self._pool.acquire() as connection, connection.transaction():
            previous = await connection.fetchrow(
                "SELECT monitored FROM registry_entities WHERE id = $1 FOR UPDATE", entity_id
            )
            if previous is None:
                return None
            await connection.execute(
                """UPDATE registry_entities
                   SET canonical_name = COALESCE($2, canonical_name),
                       coarse_type = COALESCE($3, coarse_type),
                       monitored = COALESCE($4, monitored), updated_at = now()
                   WHERE id = $1""",
                entity_id,
                canonical_name,
                coarse_type,
                monitored,
            )
            activated = monitored is True and not bool(previous["monitored"])
            if not activated:
                return 0
            return await self._enqueue_backfill(connection, entity_id, "monitoring_enabled")

    async def add_alias(self, entity_id: int, alias: str) -> int | None:
        """Approve one permanent alias and backfill if its entity is monitored."""
        async with self._pool.acquire() as connection, connection.transaction():
            monitored = await connection.fetchval(
                "SELECT monitored FROM registry_entities WHERE id = $1 FOR UPDATE", entity_id
            )
            if monitored is None:
                return None
            await self._insert_aliases(connection, entity_id, [alias])
            return (
                await self._enqueue_backfill(connection, entity_id, "alias_added")
                if bool(monitored)
                else 0
            )

    async def list_candidates(self, status: str) -> list[dict[str, Any]]:
        """List entity candidates in review priority order."""
        rows = await self._pool.fetch(
            """SELECT id, representative_mention, status, linked_entity_id,
                      occurrence_count, last_seen_at
               FROM candidate_entities WHERE status = $1
               ORDER BY occurrence_count DESC, last_seen_at DESC, id""",
            status,
        )
        return [dict(row) for row in rows]

    async def link_candidate(self, candidate_id: int, entity_id: int) -> int | None:
        """Associate occurrences and reprocess them when the target is monitored."""
        async with self._pool.acquire() as connection, connection.transaction():
            entity = await connection.fetchrow(
                "SELECT monitored FROM registry_entities WHERE id = $1", entity_id
            )
            if entity is None:
                return None
            revisions = await connection.fetch(
                """SELECT DISTINCT ON (post.id) latest.id
                   FROM post_entities AS local_entity
                   JOIN analysis_runs AS run ON run.id = local_entity.run_id
                   JOIN post_revisions AS observed ON observed.id = run.post_revision_id
                   JOIN raw_posts AS post ON post.id = observed.raw_post_id
                   JOIN post_revisions AS latest ON latest.raw_post_id = post.id
                   WHERE local_entity.candidate_entity_id = $1
                     AND post.deleted_at IS NULL AND post.inaccessible_at IS NULL
                   ORDER BY post.id, latest.revision_number DESC""",
                candidate_id,
            )
            updated = await connection.fetchval(
                """UPDATE candidate_entities SET status = 'linked', linked_entity_id = $2,
                          updated_at = now() WHERE id = $1 AND status = 'pending' RETURNING id""",
                candidate_id,
                entity_id,
            )
            if updated is None:
                return None
            await connection.execute(
                """UPDATE post_entities SET registry_entity_id = $2, candidate_entity_id = NULL
                   WHERE candidate_entity_id = $1""",
                candidate_id,
                entity_id,
            )
            if not bool(entity["monitored"]):
                return 0
            jobs = 0
            for revision in revisions:
                job_id = await connection.fetchval(
                    """INSERT INTO analysis_jobs (post_revision_id, priority, trigger_kind)
                       VALUES ($1, 'backfill', 'manual')
                       ON CONFLICT DO NOTHING RETURNING id""",
                    revision["id"],
                )
                jobs += job_id is not None
            return jobs

    async def ignore_candidate(self, candidate_id: int) -> bool:
        """Hide a pending candidate without deleting its evidence."""
        value = await self._pool.fetchval(
            """UPDATE candidate_entities SET status = 'ignored', updated_at = now()
               WHERE id = $1 AND status = 'pending' RETURNING id""",
            candidate_id,
        )
        return value is not None

    async def list_alias_candidates(self, entity_id: int) -> list[dict[str, Any]]:
        """Return pending textual forms observed for a resolved entity."""
        rows = await self._pool.fetch(
            """SELECT id, surface_form, status, occurrence_count, last_seen_at
               FROM entity_alias_candidates WHERE entity_id = $1 AND status = 'pending'
               ORDER BY occurrence_count DESC, last_seen_at DESC, id""",
            entity_id,
        )
        return [dict(row) for row in rows]

    async def review_alias_candidate(self, candidate_id: int, approve: bool) -> int | None:
        """Approve or ignore a candidate alias, backfilling approved monitored aliases."""
        async with self._pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                """SELECT candidate.entity_id, candidate.surface_form, entity.monitored
                   FROM entity_alias_candidates AS candidate
                   JOIN registry_entities AS entity ON entity.id = candidate.entity_id
                   WHERE candidate.id = $1 AND candidate.status = 'pending' FOR UPDATE""",
                candidate_id,
            )
            if row is None:
                return None
            status = "approved" if approve else "ignored"
            await connection.execute(
                "UPDATE entity_alias_candidates SET status = $2, updated_at = now() WHERE id = $1",
                candidate_id,
                status,
            )
            if not approve:
                return 0
            alias = str(row["surface_form"])
            await self._insert_aliases(connection, int(row["entity_id"]), [alias])
            return (
                await self._enqueue_backfill(connection, int(row["entity_id"]), "alias_added")
                if bool(row["monitored"])
                else 0
            )

    @staticmethod
    async def _insert_aliases(
        connection: asyncpg.Connection, entity_id: int, aliases: Sequence[str]
    ) -> None:
        for alias in aliases:
            await connection.execute(
                """INSERT INTO entity_aliases (entity_id, alias, normalized_alias)
                   VALUES ($1, $2, $3) ON CONFLICT (entity_id, alias) DO NOTHING""",
                entity_id,
                alias,
                normalize_match_text(alias),
            )

    @staticmethod
    async def _enqueue_backfill(
        connection: asyncpg.Connection, entity_id: int, trigger_kind: str
    ) -> int:
        aliases = await connection.fetch(
            """SELECT entity.id AS entity_id, entity.coarse_type, entity.monitored, alias.alias
               FROM registry_entities AS entity
               JOIN entity_aliases AS alias ON alias.entity_id = entity.id
               WHERE entity.monitored"""
        )
        rows = await connection.fetch(
            """SELECT DISTINCT ON (post.id) revision.id, revision.content
               FROM raw_posts AS post
               JOIN post_revisions AS revision ON revision.raw_post_id = post.id
               WHERE post.deleted_at IS NULL AND post.inaccessible_at IS NULL
               ORDER BY post.id, revision.revision_number DESC"""
        )
        count = 0
        for row in rows:
            if entity_id not in matched_registry_entity_ids(str(row["content"]), aliases):
                continue
            job_id = await connection.fetchval(
                """INSERT INTO analysis_jobs (post_revision_id, priority, trigger_kind)
                   VALUES ($1, 'backfill', $2) ON CONFLICT DO NOTHING RETURNING id""",
                row["id"],
                trigger_kind,
            )
            count += job_id is not None
        return count


def _unique_aliases(canonical_name: str, aliases: Sequence[str]) -> list[str]:
    values = [canonical_name, *aliases]
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        normalized = normalize_match_text(stripped)
        if stripped and normalized not in seen:
            result.append(stripped)
            seen.add(normalized)
    return result
