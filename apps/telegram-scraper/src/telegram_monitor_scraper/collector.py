"""Polling and backfill orchestration for approved channels."""

from datetime import UTC, datetime, timedelta
from typing import Protocol

from telegram_monitor_scraper.avatar_storage import ChannelAvatarStorage
from telegram_monitor_scraper.models import (
    BackfillWindow,
    ChannelFetchRequest,
    ChannelFetchResult,
    GatewayRateLimitedError,
    MonitoredChannel,
)
from telegram_monitor_scraper.repository import CollectionRepository

BACKFILL_DAYS = 365


class ChannelClient(Protocol):
    """Telegram access required by the collector, served by the Telegram gateway."""

    async def fetch(
        self, channel: MonitoredChannel, request: ChannelFetchRequest
    ) -> ChannelFetchResult: ...


class Collector:
    """Collect live posts first, then consume a bounded historical backlog.

    Each channel is read in pages. Live posts are always caught up within a run when the page
    budget allows; the one-year history arrives gradually over several runs.

    Args:
        repository: PostgreSQL collection state.
        client: Telegram gateway client.
        avatar_storage: Shared avatar volume writer.
        max_pages_per_channel: Gateway requests allowed per channel in one run.
    """

    def __init__(
        self,
        repository: CollectionRepository,
        client: ChannelClient,
        avatar_storage: ChannelAvatarStorage,
        max_pages_per_channel: int = 10,
    ) -> None:
        self._repository = repository
        self._client = client
        self._avatar_storage = avatar_storage
        self._max_pages_per_channel = max_pages_per_channel

    async def collect_once(self) -> None:
        for channel in await self._repository.active_channels():
            try:
                avatar_error = await self._collect_channel(channel)
                await self._repository.record_success(channel.id, clear_error=avatar_error is None)
            except GatewayRateLimitedError as error:
                # Every further request would hit the same Telegram limit; wait for the next run.
                await self._repository.record_error(channel.id, str(error))
                return
            except Exception as error:
                await self._repository.record_error(channel.id, str(error))

    async def _collect_channel(self, channel: MonitoredChannel) -> str | None:
        """Read a channel page by page until it is caught up or the page budget is spent.

        Args:
            channel: Source to collect.

        Returns:
            Avatar refresh error message, if the avatar could not be synchronized.
        """
        cutoff = datetime.now(UTC) - timedelta(days=BACKFILL_DAYS)
        avatar_error: str | None = None
        for page in range(self._max_pages_per_channel):
            request = await self._next_request(channel, cutoff, include_avatar=page == 0)
            result = await self._client.fetch(channel, request)
            if page == 0:
                await self._repository.update_channel_identity(
                    channel.id, result.peer_id, result.username, result.title
                )
                avatar_error = await self._apply_avatar(channel, result)
            await self._apply_live(channel, request, result)
            await self._apply_backfill(channel, request, result)
            live_done = request.live_after_message_id is None or result.newer_complete
            backfill_done = request.backfill is None or result.backfill_complete
            if live_done and backfill_done:
                break
        return avatar_error

    async def _next_request(
        self, channel: MonitoredChannel, cutoff: datetime, include_avatar: bool
    ) -> ChannelFetchRequest:
        live_after: int | None = None
        if await self._repository.live_cursor_exists(channel.id):
            live_after = await self._repository.latest_message_id(channel.id)
        backfill: BackfillWindow | None = None
        if not await self._repository.backfill_complete(channel.id):
            backfill = BackfillWindow(
                await self._repository.backfill_before_message_id(channel.id), cutoff
            )
        return ChannelFetchRequest(live_after, backfill, include_avatar)

    async def _apply_avatar(
        self, channel: MonitoredChannel, result: ChannelFetchResult
    ) -> str | None:
        """Synchronize the current avatar without blocking post collection on failure.

        Args:
            channel: Source whose profile image is synchronized.
            result: First gateway page, which always includes the avatar.

        Returns:
            Error message recorded for a failed avatar refresh, if any.
        """
        message = result.avatar_error
        if message is None:
            try:
                if result.avatar is None:
                    await self._avatar_storage.delete(channel.id)
                    await self._repository.clear_channel_avatar(channel.id)
                else:
                    await self._avatar_storage.save(channel.id, result.avatar.content)
                    await self._repository.update_channel_avatar(
                        channel.id, result.avatar.content_type
                    )
                return None
            except Exception as error:
                message = str(error)
        await self._repository.record_error(channel.id, message)
        return message

    async def _apply_live(
        self, channel: MonitoredChannel, request: ChannelFetchRequest, result: ChannelFetchResult
    ) -> None:
        if request.live_after_message_id is None:
            # A new channel starts live collection at its current head; history is backfilled.
            await self._repository.advance_live_cursor(channel.id, result.head_message_id or 0)
            return
        for post in result.newer_posts:
            await self._repository.persist_post(channel, post, "live")
            await self._repository.advance_live_cursor(channel.id, post.message_id)

    async def _apply_backfill(
        self, channel: MonitoredChannel, request: ChannelFetchRequest, result: ChannelFetchResult
    ) -> None:
        if request.backfill is None:
            return
        cursor = request.backfill.before_message_id
        for post in result.older_posts:
            await self._repository.persist_post(channel, post, "backfill")
            await self._repository.advance_backfill_cursor(
                channel.id, post.message_id, complete=False
            )
            cursor = post.message_id
        if result.backfill_complete:
            await self._repository.advance_backfill_cursor(channel.id, cursor, complete=True)
