"""Read-only investigation queries for the product web interface."""

from datetime import datetime
from typing import Any

import asyncpg


class AnalyticsRepository:
    """Expose auditable aggregates backed only by fully completed analysis runs."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def dashboard(self, start: datetime | None, end: datetime | None) -> dict[str, Any]:
        """Return the current monitoring overview."""
        rows = await self._pool.fetch(_ENTITY_SUMMARY_SQL, start, end)
        channels = await self._pool.fetch(_CHANNEL_SUMMARY_SQL, start, end)
        return {
            "entities": [dict(row) for row in rows],
            "channels": [dict(row) for row in channels],
        }

    async def entity(
        self, entity_id: int, start: datetime | None, end: datetime | None
    ) -> dict[str, Any] | None:
        """Return a monitored entity and its channel-level evidence aggregate."""
        entity = await self._pool.fetchrow(
            """SELECT id, canonical_name, coarse_type FROM registry_entities
               WHERE id = $1 AND monitored = true""",
            entity_id,
        )
        if entity is None:
            return None
        channels = await self._pool.fetch(_ENTITY_CHANNEL_SQL, entity_id, start, end)
        incomplete = await self._pool.fetchval(_INCOMPLETE_SQL, entity_id, start, end)
        return {
            "entity": dict(entity),
            "channels": [dict(row) for row in channels],
            "incomplete_posts": int(incomplete or 0),
        }

    async def evidence(
        self,
        entity_id: int,
        channel_id: int | None,
        stance: str | None,
        start: datetime | None,
        end: datetime | None,
    ) -> list[dict[str, Any]]:
        """Return claims that support a selected entity aggregate."""
        rows = await self._pool.fetch(_EVIDENCE_SQL, entity_id, channel_id, stance, start, end)
        return [dict(row) for row in rows]

    async def channels(self, start: datetime | None, end: datetime | None) -> list[dict[str, Any]]:
        """Return channel profiles for comparison."""
        rows = await self._pool.fetch(_CHANNEL_SUMMARY_SQL, start, end)
        return [dict(row) for row in rows]

    async def post(self, raw_post_id: int) -> dict[str, Any] | None:
        """Return the latest accessible post plus its completed extraction evidence."""
        row = await self._pool.fetchrow(_POST_SQL, raw_post_id)
        return dict(row) if row is not None else None


def _base(start_arg: str, end_arg: str) -> str:
    """Build the shared completed-analysis predicate with positional query parameters."""
    return f"""
FROM claim_target_classifications AS classification
JOIN claims AS claim ON claim.id = classification.claim_id
JOIN post_entities AS post_entity ON post_entity.id = classification.post_entity_id
JOIN analysis_runs AS run ON run.id = claim.run_id AND run.status = 'completed'
JOIN post_revisions AS revision ON revision.id = run.post_revision_id
JOIN raw_posts AS post ON post.id = revision.raw_post_id
JOIN monitored_channels AS channel ON channel.id = post.channel_id
JOIN registry_entities AS entity ON entity.id = post_entity.registry_entity_id
WHERE entity.monitored = true AND post.deleted_at IS NULL AND post.inaccessible_at IS NULL
  AND revision.id = (
      SELECT latest.id FROM post_revisions AS latest
      WHERE latest.raw_post_id = post.id ORDER BY latest.revision_number DESC LIMIT 1
  )
  AND ({start_arg}::timestamptz IS NULL OR post.published_at >= {start_arg})
  AND ({end_arg}::timestamptz IS NULL OR post.published_at < {end_arg})
"""


_ENTITY_SUMMARY_SQL = (
    """
SELECT entity.id, entity.canonical_name, count(DISTINCT claim.id) AS claim_count,
       count(DISTINCT post.id) AS post_count,
       count(*) FILTER (WHERE classification.stance = 'позитивне') AS positive_count,
       count(*) FILTER (WHERE classification.stance = 'негативне') AS negative_count,
       count(*) FILTER (WHERE classification.stance = 'відсутнє') AS absent_count
"""
    + _base("$1", "$2")
    + ("GROUP BY entity.id, entity.canonical_name ORDER BY claim_count DESC, entity.canonical_name")
)

_CHANNEL_SUMMARY_SQL = (
    """
SELECT channel.id, channel.title, channel.username, channel.avatar_url,
       count(DISTINCT claim.id) AS claim_count, count(DISTINCT post.id) AS post_count,
       count(*) FILTER (WHERE classification.stance = 'позитивне') AS positive_count,
       count(*) FILTER (WHERE classification.stance = 'негативне') AS negative_count,
       count(*) FILTER (WHERE classification.stance = 'відсутнє') AS absent_count
"""
    + _base("$1", "$2")
    + (
        "GROUP BY channel.id, channel.title, channel.username, channel.avatar_url "
        "ORDER BY claim_count DESC"
    )
)

_ENTITY_CHANNEL_SQL = (
    """
SELECT channel.id, channel.title, channel.username, channel.avatar_url,
       count(DISTINCT claim.id) AS claim_count, count(DISTINCT post.id) AS post_count,
       count(*) FILTER (WHERE classification.stance = 'позитивне') AS positive_count,
       count(*) FILTER (WHERE classification.stance = 'негативне') AS negative_count,
       count(*) FILTER (WHERE classification.stance = 'відсутнє') AS absent_count
"""
    + _base("$2", "$3")
    + " AND entity.id = $1 "
    + (
        "GROUP BY channel.id, channel.title, channel.username, channel.avatar_url "
        "ORDER BY claim_count DESC"
    )
)

_INCOMPLETE_SQL = """
SELECT count(DISTINCT post.id)
FROM raw_posts AS post
JOIN post_revisions AS revision ON revision.raw_post_id = post.id
JOIN analysis_runs AS run ON run.post_revision_id = revision.id
JOIN post_entities AS post_entity ON post_entity.run_id = run.id
WHERE post_entity.registry_entity_id = $1
  AND post.deleted_at IS NULL AND post.inaccessible_at IS NULL
  AND revision.id = (
      SELECT latest.id FROM post_revisions AS latest
      WHERE latest.raw_post_id = post.id ORDER BY latest.revision_number DESC LIMIT 1
  )
  AND run.status <> 'completed'
  AND ($2::timestamptz IS NULL OR post.published_at >= $2)
  AND ($3::timestamptz IS NULL OR post.published_at < $3)
"""

_EVIDENCE_SQL = (
    """
SELECT claim.id AS claim_id, claim.normalized_text, claim.evidence_text, claim.epistemic_status,
       classification.stance, classification.rhetoric, post.id AS post_id, post.published_at,
       channel.id AS channel_id, channel.title AS channel_title
"""
    + _base("$4", "$5")
    + """
  AND entity.id = $1 AND ($2::bigint IS NULL OR channel.id = $2)
  AND ($3::text IS NULL OR classification.stance = $3)
ORDER BY post.published_at DESC, claim.id DESC
"""
)

_POST_SQL = """
SELECT post.id, post.telegram_message_id, post.published_at, revision.content,
       channel.id AS channel_id,
       channel.title AS channel_title, channel.username,
       COALESCE(jsonb_agg(DISTINCT jsonb_build_object(
           'id', claim.id, 'text', claim.normalized_text, 'evidence', claim.evidence_text,
           'epistemic_status', claim.epistemic_status, 'stance', classification.stance,
           'rhetoric', classification.rhetoric, 'entity', entity.canonical_name
       )) FILTER (WHERE claim.id IS NOT NULL), '[]'::jsonb) AS claims
FROM raw_posts AS post
JOIN monitored_channels AS channel ON channel.id = post.channel_id
JOIN LATERAL (
    SELECT * FROM post_revisions WHERE raw_post_id = post.id ORDER BY revision_number DESC LIMIT 1
) AS revision ON true
LEFT JOIN analysis_runs AS run ON run.post_revision_id = revision.id AND run.status = 'completed'
LEFT JOIN claims AS claim ON claim.run_id = run.id
LEFT JOIN claim_target_classifications AS classification ON classification.claim_id = claim.id
LEFT JOIN post_entities AS post_entity ON post_entity.id = classification.post_entity_id
LEFT JOIN registry_entities AS entity ON entity.id = post_entity.registry_entity_id
WHERE post.id = $1 AND post.deleted_at IS NULL AND post.inaccessible_at IS NULL
GROUP BY post.id, post.telegram_message_id, post.published_at, revision.content, channel.id,
         channel.title, channel.username
"""
