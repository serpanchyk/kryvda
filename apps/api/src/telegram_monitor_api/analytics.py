"""Read-only analytical queries for the Kryvda investigation interface."""
# ruff: noqa: E501

from datetime import datetime
from typing import Any, Literal

import asyncpg


class AnalyticsRepository:
    """Expose completed-analysis aggregates without mutating operational data."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def dashboard(self, start: datetime | None, end: datetime | None) -> dict[str, Any]:
        """Return the operational overview for a selected time range."""
        summary = await self._pool.fetchrow(_DASHBOARD_SUMMARY_SQL, start, end)
        daily = await self._pool.fetch(_DAILY_SQL, start, end)
        entities = await self._pool.fetch(_ENTITY_SUMMARY_SQL, start, end)
        channels = await self._pool.fetch(_CHANNEL_SUMMARY_SQL, start, end)
        pipeline = await self._pool.fetchrow(_PIPELINE_SQL)
        return {
            "summary": dict(summary) if summary is not None else _empty_summary(),
            "daily": [dict(row) for row in daily],
            "entities": [dict(row) for row in entities],
            "channels": [dict(row) for row in channels],
            "pipeline": dict(pipeline) if pipeline is not None else _empty_pipeline(),
        }

    async def entity(
        self, entity_id: int, start: datetime | None, end: datetime | None, limit: int, offset: int
    ) -> dict[str, Any] | None:
        """Return one registry entity with its evidence and temporal aggregates."""
        entity = await self._pool.fetchrow(_ENTITY_SQL, entity_id)
        if entity is None:
            return None
        channels = await self._pool.fetch(
            _ENTITY_CHANNEL_PAGE_SQL, entity_id, start, end, limit, offset
        )
        channel_options = await self._pool.fetch(_ENTITY_CHANNEL_OPTIONS_SQL, entity_id, start, end)
        channel_total = await self._pool.fetchval(_ENTITY_CHANNEL_COUNT_SQL, entity_id, start, end)
        summary = await self._pool.fetchrow(_ENTITY_TOTAL_SQL, entity_id, start, end)
        daily = await self._pool.fetch(_ENTITY_DAILY_SQL, entity_id, start, end)
        incomplete = await self._pool.fetchval(_INCOMPLETE_SQL, entity_id, start, end)
        return {
            "entity": dict(entity),
            "summary": dict(summary)
            if summary is not None
            else {"mention_count": 0, "positive_count": 0, "negative_count": 0},
            "channels": {
                "items": [dict(row) for row in channels],
                "total": int(channel_total or 0),
                "limit": limit,
                "offset": offset,
            },
            "channel_options": [dict(row) for row in channel_options],
            "daily": [dict(row) for row in daily],
            "incomplete_posts": int(incomplete or 0),
        }

    async def evidence(
        self,
        entity_id: int,
        channel_id: int | None,
        stance: str | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        args = (entity_id, channel_id, stance, start, end, limit, offset)
        rows = await self._pool.fetch(_EVIDENCE_PAGE_SQL, *args)
        total = await self._pool.fetchval(_EVIDENCE_COUNT_SQL, *args[:5])
        return {
            "items": [dict(row) for row in rows],
            "total": int(total or 0),
            "limit": limit,
            "offset": offset,
        }

    async def channels(
        self, start: datetime | None, end: datetime | None, limit: int, offset: int
    ) -> dict[str, Any]:
        """Return channel comparison rows and daily activity."""
        rows = await self._pool.fetch(_CHANNEL_PAGE_SQL, start, end, limit, offset)
        total = await self._pool.fetchval(_CHANNEL_COUNT_SQL, start, end)
        daily = await self._pool.fetch(_DAILY_SQL, start, end)
        return {
            "items": [dict(row) for row in rows],
            "total": int(total or 0),
            "limit": limit,
            "offset": offset,
            "daily": [dict(row) for row in daily],
        }

    async def claims(
        self,
        search: str | None,
        entity_id: int | None,
        channel_id: int | None,
        stance: str | None,
        start: datetime | None,
        end: datetime | None,
        sort: Literal["newest", "oldest"],
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        """Return a page of auditable claims with controlled ordering."""
        order = "ASC" if sort == "oldest" else "DESC"
        args = (search, entity_id, channel_id, stance, start, end, limit, offset)
        rows = await self._pool.fetch(_CLAIMS_SQL.format(order=order), *args)
        total = await self._pool.fetchval(_CLAIMS_COUNT_SQL, *args[:6])
        return {
            "items": [dict(row) for row in rows],
            "total": int(total or 0),
            "limit": limit,
            "offset": offset,
        }

    async def post(self, raw_post_id: int) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(_POST_SQL, raw_post_id)
        return dict(row) if row is not None else None


def _empty_summary() -> dict[str, int]:
    return {
        "post_count": 0,
        "claim_count": 0,
        "entity_count": 0,
        "channel_count": 0,
        "positive_count": 0,
        "negative_count": 0,
        "absent_count": 0,
        "today_post_count": 0,
        "today_claim_count": 0,
    }


def _empty_pipeline() -> dict[str, int | None]:
    return {
        "pending_live": 0,
        "pending_backfill": 0,
        "leased": 0,
        "failed": 0,
        "completed_last_hour": 0,
        "failed_last_hour": 0,
        "last_completed_at": None,
    }


def _base(start_arg: str, end_arg: str) -> str:
    return f"""
FROM claim_target_classifications AS classification
JOIN claims AS claim ON claim.id = classification.claim_id
JOIN post_entities AS post_entity ON post_entity.id = classification.post_entity_id
JOIN analysis_runs AS run ON run.id = claim.run_id AND run.status = 'completed'
JOIN post_revisions AS revision ON revision.id = run.post_revision_id
JOIN raw_posts AS post ON post.id = revision.raw_post_id
JOIN monitored_channels AS channel ON channel.id = post.channel_id
JOIN registry_entities AS entity ON entity.id = post_entity.registry_entity_id
WHERE post.deleted_at IS NULL AND post.inaccessible_at IS NULL
  AND revision.id = (SELECT latest.id FROM post_revisions AS latest
                     WHERE latest.raw_post_id = post.id
                     ORDER BY latest.revision_number DESC LIMIT 1)
  AND ({start_arg}::timestamptz IS NULL OR post.published_at >= {start_arg})
  AND ({end_arg}::timestamptz IS NULL OR post.published_at < {end_arg})
"""


_DASHBOARD_SUMMARY_SQL = """SELECT count(DISTINCT post.id) AS post_count,
    count(DISTINCT claim.id) AS claim_count, count(DISTINCT entity.id) AS entity_count,
    count(DISTINCT channel.id) AS channel_count,
    count(*) FILTER (WHERE classification.stance = 'позитивне') AS positive_count,
    count(*) FILTER (WHERE classification.stance = 'негативне') AS negative_count,
    count(*) FILTER (WHERE classification.stance = 'відсутнє') AS absent_count,
    count(DISTINCT post.id) FILTER (WHERE post.published_at >= date_trunc('day', now()))
        AS today_post_count,
    count(DISTINCT claim.id) FILTER (WHERE post.published_at >= date_trunc('day', now()))
        AS today_claim_count
""" + _base("$1", "$2")

_DAILY_SQL = (
    """SELECT date_trunc('day', post.published_at)::date AS date,
    count(DISTINCT post.id) AS post_count, count(DISTINCT claim.id) AS claim_count,
    count(*) FILTER (WHERE classification.stance = 'позитивне') AS positive_count,
    count(*) FILTER (WHERE classification.stance = 'негативне') AS negative_count,
    count(*) FILTER (WHERE classification.stance = 'відсутнє') AS absent_count
"""
    + _base("$1", "$2")
    + "GROUP BY 1 ORDER BY 1"
)

_ENTITY_SUMMARY_SQL = (
    """SELECT entity.id, entity.canonical_name,
    count(DISTINCT claim.id) AS claim_count, count(DISTINCT post.id) AS post_count,
    count(*) FILTER (WHERE classification.stance = 'позитивне') AS positive_count,
    count(*) FILTER (WHERE classification.stance = 'негативне') AS negative_count,
    count(*) FILTER (WHERE classification.stance = 'відсутнє') AS absent_count
"""
    + _base("$1", "$2")
    + "GROUP BY entity.id, entity.canonical_name ORDER BY claim_count DESC, entity.canonical_name"
)

_CHANNEL_SUMMARY_SQL = (
    """SELECT channel.id, channel.title, channel.username, channel.avatar_url,
    channel.status, max(post.published_at) AS last_published_at,
    count(DISTINCT entity.id) AS entity_count, count(DISTINCT claim.id) AS claim_count,
    count(DISTINCT post.id) AS post_count,
    count(*) FILTER (WHERE classification.stance = 'позитивне') AS positive_count,
    count(*) FILTER (WHERE classification.stance = 'негативне') AS negative_count,
    count(*) FILTER (WHERE classification.stance = 'відсутнє') AS absent_count
"""
    + _base("$1", "$2")
    + "GROUP BY channel.id, channel.title, channel.username, channel.avatar_url, channel.status ORDER BY claim_count DESC"
)
_CHANNEL_PAGE_SQL = _CHANNEL_SUMMARY_SQL + " LIMIT $3 OFFSET $4"
_CHANNEL_COUNT_SQL = "SELECT count(DISTINCT channel.id) " + _base("$1", "$2")

_PIPELINE_SQL = """SELECT count(*) FILTER (WHERE status = 'pending' AND priority = 'live') AS pending_live,
    count(*) FILTER (WHERE status = 'pending' AND priority = 'backfill') AS pending_backfill,
    count(*) FILTER (WHERE status = 'leased') AS leased, count(*) FILTER (WHERE status = 'failed') AS failed,
    (SELECT count(*) FROM analysis_runs WHERE status = 'completed' AND completed_at >= now() - interval '1 hour') AS completed_last_hour,
    (SELECT count(*) FROM analysis_runs WHERE status = 'failed' AND completed_at >= now() - interval '1 hour') AS failed_last_hour,
    (SELECT max(completed_at) FROM analysis_runs WHERE status = 'completed') AS last_completed_at
FROM analysis_jobs"""

_ENTITY_SQL = """SELECT entity.id, entity.canonical_name, entity.coarse_type, entity.monitored
FROM registry_entities AS entity WHERE entity.id = $1"""

_ENTITY_CHANNEL_SQL = (
    """SELECT channel.id, channel.title, channel.username, channel.avatar_url,
    channel.status, max(post.published_at) AS last_published_at,
    count(DISTINCT entity.id) AS entity_count,
    count(DISTINCT claim.id) FILTER (WHERE classification.stance IN ('позитивне', 'негативне'))
        AS claim_count,
    count(DISTINCT post.id) AS post_count,
    count(*) FILTER (WHERE classification.stance = 'позитивне') AS positive_count,
    count(*) FILTER (WHERE classification.stance = 'негативне') AS negative_count,
    0 AS absent_count
"""
    + _base("$2", "$3")
    + """ AND entity.id = $1 AND classification.stance IN ('позитивне', 'негативне')
GROUP BY channel.id, channel.title, channel.username, channel.avatar_url, channel.status
ORDER BY claim_count DESC"""
)
_ENTITY_CHANNEL_PAGE_SQL = _ENTITY_CHANNEL_SQL + " LIMIT $4 OFFSET $5"
_ENTITY_CHANNEL_COUNT_SQL = (
    "SELECT count(DISTINCT channel.id) "
    + _base("$2", "$3")
    + " AND entity.id = $1 AND classification.stance IN ('позитивне', 'негативне')"
)
_ENTITY_CHANNEL_OPTIONS_SQL = (
    "SELECT DISTINCT channel.id, channel.title "
    + _base("$2", "$3")
    + " AND entity.id = $1 AND classification.stance IN ('позитивне', 'негативне') "
    + "ORDER BY channel.title"
)

_ENTITY_DAILY_SQL = (
    """SELECT date_trunc('day', post.published_at)::date AS date,
    count(DISTINCT post.id) AS post_count,
    count(DISTINCT claim.id) FILTER (WHERE classification.stance IN ('позитивне', 'негативне'))
        AS claim_count,
    count(*) FILTER (WHERE classification.stance = 'позитивне') AS positive_count,
    count(*) FILTER (WHERE classification.stance = 'негативне') AS negative_count,
    0 AS absent_count
"""
    + _base("$2", "$3")
    + " AND entity.id = $1 GROUP BY 1 ORDER BY 1"
)

_ENTITY_TOTAL_SQL = (
    """SELECT count(DISTINCT claim.id) AS mention_count,
    count(*) FILTER (WHERE classification.stance = 'позитивне') AS positive_count,
    count(*) FILTER (WHERE classification.stance = 'негативне') AS negative_count
"""
    + _base("$2", "$3")
    + " AND entity.id = $1 AND classification.stance IN ('позитивне', 'негативне')"
)

_INCOMPLETE_SQL = """SELECT count(DISTINCT post.id) FROM raw_posts AS post
JOIN post_revisions AS revision ON revision.raw_post_id = post.id
JOIN analysis_runs AS run ON run.post_revision_id = revision.id
JOIN post_entities AS post_entity ON post_entity.run_id = run.id
WHERE post_entity.registry_entity_id = $1 AND post.deleted_at IS NULL AND post.inaccessible_at IS NULL
  AND revision.id = (SELECT latest.id FROM post_revisions AS latest WHERE latest.raw_post_id = post.id ORDER BY latest.revision_number DESC LIMIT 1)
  AND run.status <> 'completed' AND ($2::timestamptz IS NULL OR post.published_at >= $2)
  AND ($3::timestamptz IS NULL OR post.published_at < $3)"""

_EVIDENCE_SQL = (
    """SELECT claim.id AS claim_id, claim.normalized_text, claim.evidence_text,
    claim.epistemic_status, classification.stance, classification.rhetoric, post.id AS post_id,
    post.published_at, channel.id AS channel_id, channel.title AS channel_title
"""
    + _base("$4", "$5")
    + """ AND entity.id = $1 AND classification.stance IN ('позитивне', 'негативне')
  AND ($2::bigint IS NULL OR channel.id = $2)
  AND ($3::text IS NULL OR classification.stance = $3) ORDER BY post.published_at DESC, claim.id DESC"""
)
_EVIDENCE_PAGE_SQL = _EVIDENCE_SQL + " LIMIT $6 OFFSET $7"
_EVIDENCE_COUNT_SQL = (
    "SELECT count(*) "
    + _base("$4", "$5")
    + """ AND entity.id = $1 AND classification.stance IN ('позитивне', 'негативне')
  AND ($2::bigint IS NULL OR channel.id = $2) AND ($3::text IS NULL OR classification.stance = $3)"""
)

_CLAIMS_BASE = (
    _base("$5", "$6")
    + """ AND ($1::text IS NULL OR claim.normalized_text ILIKE '%' || $1 || '%'
    OR entity.canonical_name ILIKE '%' || $1 || '%') AND ($2::bigint IS NULL OR entity.id = $2)
  AND ($3::bigint IS NULL OR channel.id = $3) AND ($4::text IS NULL OR classification.stance = $4)"""
)
_CLAIMS_SQL = (
    """SELECT claim.id AS claim_id, claim.normalized_text, claim.evidence_text,
    classification.stance, post.id AS post_id, post.published_at, channel.id AS channel_id,
    channel.title AS channel_title, entity.id AS entity_id, entity.canonical_name AS entity_name
"""
    + _CLAIMS_BASE
    + " ORDER BY post.published_at {order}, claim.id {order} LIMIT $7 OFFSET $8"
)
_CLAIMS_COUNT_SQL = "SELECT count(*) " + _CLAIMS_BASE

_POST_SQL = """SELECT post.id, post.telegram_message_id, post.published_at, revision.content,
    channel.id AS channel_id, channel.title AS channel_title, channel.username,
    COALESCE(jsonb_agg(DISTINCT jsonb_build_object('id', claim.id, 'text', claim.normalized_text,
        'evidence', claim.evidence_text, 'epistemic_status', claim.epistemic_status,
        'stance', classification.stance, 'rhetoric', classification.rhetoric,
        'entity', entity.canonical_name)) FILTER (WHERE claim.id IS NOT NULL), '[]'::jsonb) AS claims
FROM raw_posts AS post JOIN monitored_channels AS channel ON channel.id = post.channel_id
JOIN LATERAL (SELECT * FROM post_revisions WHERE raw_post_id = post.id ORDER BY revision_number DESC LIMIT 1) AS revision ON true
LEFT JOIN analysis_runs AS run ON run.post_revision_id = revision.id AND run.status = 'completed'
LEFT JOIN claims AS claim ON claim.run_id = run.id LEFT JOIN claim_target_classifications AS classification ON classification.claim_id = claim.id
LEFT JOIN post_entities AS post_entity ON post_entity.id = classification.post_entity_id
LEFT JOIN registry_entities AS entity ON entity.id = post_entity.registry_entity_id
WHERE post.id = $1 AND post.deleted_at IS NULL AND post.inaccessible_at IS NULL
GROUP BY post.id, post.telegram_message_id, post.published_at, revision.content, channel.id, channel.title, channel.username"""
