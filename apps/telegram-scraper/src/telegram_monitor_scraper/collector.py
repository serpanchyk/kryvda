"""Polling and backfill orchestration for approved channels."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Protocol

from telegram_monitor_scraper.models import MonitoredChannel, TelegramPost
from telegram_monitor_scraper.repository import CollectionRepository


class ChannelClient(Protocol):
    """Minimal Telegram operations required by the collector."""

    def newer_posts(
        self, channel: MonitoredChannel, minimum_message_id: int
    ) -> AsyncIterator[TelegramPost]: ...

    def older_posts(
        self, channel: MonitoredChannel, before_message_id: int | None
    ) -> AsyncIterator[TelegramPost]: ...

    async def newest_message_id(self, channel: MonitoredChannel) -> int: ...

    async def resolve(self, channel: MonitoredChannel) -> tuple[int, str | None, str | None]: ...


class Collector:
    """Collect live posts first, then consume a bounded historical backlog."""

    def __init__(self, repository: CollectionRepository, client: ChannelClient) -> None:
        self._repository = repository
        self._client = client

    async def collect_once(self) -> None:
        for channel in await self._repository.active_channels():
            try:
                peer_id, username, title = await self._client.resolve(channel)
                await self._repository.update_channel_identity(channel.id, peer_id, username, title)
                await self._collect_live(channel)
                await self._collect_backfill(channel)
                await self._repository.record_success(channel.id)
            except Exception as error:
                await self._repository.record_error(channel.id, str(error))

    async def _collect_live(self, channel: MonitoredChannel) -> None:
        if not await self._repository.live_cursor_exists(channel.id):
            await self._repository.advance_live_cursor(
                channel.id, await self._client.newest_message_id(channel)
            )
            return
        cursor = await self._repository.latest_message_id(channel.id)
        async for post in self._client.newer_posts(channel, cursor):
            await self._repository.persist_post(channel, post, "live")
            await self._repository.advance_live_cursor(channel.id, post.message_id)

    async def _collect_backfill(self, channel: MonitoredChannel) -> None:
        if await self._repository.backfill_complete(channel.id):
            return
        cutoff = datetime.now(UTC) - timedelta(days=365)
        before_message_id = await self._repository.backfill_before_message_id(channel.id)
        async for post in self._client.older_posts(channel, before_message_id):
            if post.published_at < cutoff:
                await self._repository.advance_backfill_cursor(
                    channel.id, post.message_id, complete=True
                )
                return
            await self._repository.persist_post(channel, post, "backfill")
            await self._repository.advance_backfill_cursor(
                channel.id, post.message_id, complete=False
            )
        await self._repository.advance_backfill_cursor(channel.id, before_message_id, complete=True)
