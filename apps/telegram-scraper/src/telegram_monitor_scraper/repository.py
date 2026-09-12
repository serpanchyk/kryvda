"""PostgreSQL persistence for Telegram collection."""

import json
from datetime import UTC, datetime
from typing import cast

import asyncpg
from monitoring_common.contracts import alias_occurs

from telegram_monitor_scraper.models import MonitoredChannel, TelegramPost


class CollectionRepository:
    """Own the scraper's durable cursors, evidence, jobs, and health state."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def active_channels(self) -> list[MonitoredChannel]:
        rows = await self._pool.fetch(
            """SELECT id, configured_reference, telegram_peer_id, access_kind
               FROM monitored_channels WHERE status = 'active' ORDER BY id"""
        )
        return [MonitoredChannel(**dict(row)) for row in rows]

    async def update_channel_identity(
        self, channel_id: int, peer_id: int, username: str | None, title: str | None
    ) -> None:
        """Refresh mutable display data while anchoring the source to its stable peer ID."""
        await self._pool.execute(
            """UPDATE monitored_channels
               SET telegram_peer_id = $2, username = $3, title = $4, updated_at = now()
               WHERE id = $1""",
            channel_id,
            peer_id,
            username,
            title,
        )

    async def update_channel_avatar(self, channel_id: int, content_type: str) -> None:
        """Record the API URL and media type for a stored current avatar.

        Args:
            channel_id: Internal monitored-channel identifier.
            content_type: MIME type detected from the stored image.
        """
        await self._pool.execute(
            """UPDATE monitored_channels
               SET avatar_url = '/channel-images/' || $1, avatar_content_type = $2,
                   avatar_updated_at = now(), updated_at = now()
               WHERE id = $1""",
            channel_id,
            content_type,
        )

    async def clear_channel_avatar(self, channel_id: int) -> None:
        """Clear metadata after Telegram reports no current profile image.

        Args:
            channel_id: Internal monitored-channel identifier.
        """
        await self._pool.execute(
            """UPDATE monitored_channels
               SET avatar_url = NULL, avatar_content_type = NULL, avatar_updated_at = NULL,
                   updated_at = now()
               WHERE id = $1""",
            channel_id,
        )

    async def latest_message_id(self, channel_id: int) -> int:
        value = await self._pool.fetchval(
            "SELECT latest_message_id FROM collection_cursors WHERE channel_id = $1", channel_id
        )
        return int(value or 0)

    async def live_cursor_exists(self, channel_id: int) -> bool:
        """Tell initial live-cursor establishment from a legitimate zero cursor."""
        value = await self._pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM collection_cursors WHERE channel_id = $1)",
            channel_id,
        )
        return bool(value)

    async def backfill_before_message_id(self, channel_id: int) -> int | None:
        value = await self._pool.fetchval(
            "SELECT backfill_before_message_id FROM collection_cursors WHERE channel_id = $1",
            channel_id,
        )
        return cast(int | None, value)

    async def backfill_complete(self, channel_id: int) -> bool:
        value = await self._pool.fetchval(
            "SELECT backfill_completed_at IS NOT NULL "
            "FROM collection_cursors WHERE channel_id = $1",
            channel_id,
        )
        return bool(value)

    async def persist_post(
        self, channel: MonitoredChannel, post: TelegramPost, priority: str
    ) -> bool:
        """Persist immutable evidence and enqueue analysis only for a new text revision."""
        async with self._pool.acquire() as connection, connection.transaction():
            raw_post_id = await connection.fetchval(
                """INSERT INTO raw_posts (channel_id, telegram_message_id, published_at, metadata)
                   VALUES ($1, $2, $3, $4::jsonb)
                   ON CONFLICT (channel_id, telegram_message_id) DO UPDATE
                   SET metadata = EXCLUDED.metadata
                   RETURNING id""",
                channel.id,
                post.message_id,
                post.published_at,
                json.dumps(post.metadata),
            )
            latest = await connection.fetchrow(
                """SELECT id, content, edited_at FROM post_revisions
                   WHERE raw_post_id = $1 ORDER BY revision_number DESC LIMIT 1""",
                raw_post_id,
            )
            if (
                latest
                and latest["content"] == post.content
                and latest["edited_at"] == post.edited_at
            ):
                return False
            revision_number = (
                1
                if latest is None
                else await connection.fetchval(
                    "SELECT MAX(revision_number) + 1 FROM post_revisions WHERE raw_post_id = $1",
                    raw_post_id,
                )
            )
            revision_id = await connection.fetchval(
                """INSERT INTO post_revisions
                   (raw_post_id, revision_number, content, edited_at, attachments)
                   VALUES ($1, $2, $3, $4, $5::jsonb) RETURNING id""",
                raw_post_id,
                revision_number,
                post.content,
                post.edited_at,
                json.dumps(post.attachments),
            )
            aliases = await connection.fetch(
                """SELECT alias.alias FROM entity_aliases AS alias
                   JOIN registry_entities AS entity ON entity.id = alias.entity_id
                   WHERE entity.monitored"""
            )
            if post.content.strip() and any(
                alias_occurs(post.content, str(row["alias"])) for row in aliases
            ):
                await connection.execute(
                    """INSERT INTO analysis_jobs (post_revision_id, priority, trigger_kind)
                       VALUES ($1, $2, 'collection') ON CONFLICT DO NOTHING""",
                    revision_id,
                    priority,
                )
            return True

    async def advance_live_cursor(self, channel_id: int, message_id: int) -> None:
        await self._pool.execute(
            """INSERT INTO collection_cursors (channel_id, latest_message_id)
               VALUES ($1, $2) ON CONFLICT (channel_id) DO UPDATE
               SET latest_message_id = GREATEST(
                   collection_cursors.latest_message_id, EXCLUDED.latest_message_id
               ),
                   updated_at = now()""",
            channel_id,
            message_id,
        )

    async def advance_backfill_cursor(
        self, channel_id: int, message_id: int | None, complete: bool
    ) -> None:
        await self._pool.execute(
            """INSERT INTO collection_cursors
               (channel_id, backfill_before_message_id, backfill_completed_at)
               VALUES ($1, $2, CASE WHEN $3 THEN now() ELSE NULL END)
               ON CONFLICT (channel_id) DO UPDATE
               SET backfill_before_message_id = EXCLUDED.backfill_before_message_id,
                   backfill_completed_at = CASE WHEN $3 THEN now()
                       ELSE collection_cursors.backfill_completed_at END,
                   updated_at = now()""",
            channel_id,
            message_id,
            complete,
        )

    async def record_success(self, channel_id: int, clear_error: bool = True) -> None:
        """Record completed post collection while retaining a simultaneous avatar failure.

        Args:
            channel_id: Internal monitored-channel identifier.
            clear_error: Whether this collection cycle completed without an avatar error.
        """
        await self._pool.execute(
            """UPDATE monitored_channels
               SET last_collected_at = now(),
                   last_error = CASE WHEN $2 THEN NULL ELSE last_error END,
                   last_error_at = CASE WHEN $2 THEN NULL ELSE last_error_at END,
                   updated_at = now()
               WHERE id = $1""",
            channel_id,
            clear_error,
        )

    async def record_error(self, channel_id: int, message: str) -> None:
        await self._pool.execute(
            """UPDATE monitored_channels SET last_error = $2, last_error_at = now(),
               updated_at = now()
               WHERE id = $1""",
            channel_id,
            message[:1000],
        )

    async def mark_deleted(self, channel_id: int, message_ids: list[int]) -> None:
        if message_ids:
            await self._pool.execute(
                """UPDATE raw_posts SET deleted_at = COALESCE(deleted_at, $2)
                   WHERE channel_id = $1 AND telegram_message_id = ANY($3::bigint[])""",
                channel_id,
                datetime.now(UTC),
                message_ids,
            )
