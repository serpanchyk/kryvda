"""Telethon adapter isolated from collection orchestration."""

from collections.abc import AsyncIterator
from typing import Any

from telethon import TelegramClient
from telethon.sessions import StringSession

from telegram_monitor_scraper.models import MonitoredChannel, TelegramPost


class TelethonChannelClient:
    """Read channel messages through an authorized MTProto user session."""

    def __init__(self, api_id: int, api_hash: str, session_string: str) -> None:
        self._client = TelegramClient(StringSession(session_string), api_id, api_hash)

    async def connect(self, phone_number: str) -> None:
        await self._client.connect()
        if not await self._client.is_user_authorized():
            raise RuntimeError(
                "Telegram session is not authorized; generate TELEGRAM_SESSION_STRING "
                "with the login command"
            )

    async def disconnect(self) -> None:
        await self._client.disconnect()

    async def resolve(self, channel: MonitoredChannel) -> tuple[int, str | None, str | None]:
        """Resolve a configured handle and return durable identity plus current display data."""
        entity = await self._client.get_entity(self._entity_reference(channel))
        return int(entity.id), getattr(entity, "username", None), getattr(entity, "title", None)

    async def newer_posts(
        self, channel: MonitoredChannel, minimum_message_id: int
    ) -> AsyncIterator[TelegramPost]:
        entity = await self._client.get_entity(self._entity_reference(channel))
        async for message in self._client.iter_messages(
            entity, min_id=minimum_message_id, reverse=True
        ):
            yield self._to_post(message)

    async def newest_message_id(self, channel: MonitoredChannel) -> int:
        """Return the current head without walking a channel's full history."""
        entity = await self._client.get_entity(self._entity_reference(channel))
        messages = await self._client.get_messages(entity, limit=1)
        return int(messages[0].id) if messages else 0

    async def older_posts(
        self, channel: MonitoredChannel, before_message_id: int | None
    ) -> AsyncIterator[TelegramPost]:
        entity = await self._client.get_entity(self._entity_reference(channel))
        kwargs = {} if before_message_id is None else {"max_id": before_message_id}
        async for message in self._client.iter_messages(entity, **kwargs):
            yield self._to_post(message)

    @staticmethod
    def _entity_reference(channel: MonitoredChannel) -> int | str:
        """Select a Telethon-resolvable reference for a monitored source.

        Args:
            channel: Source whose Telegram entity will be fetched.

        Returns:
            Public handle or a private source's durable peer identifier.
        """
        if channel.access_kind == "public":
            return channel.configured_reference
        return channel.telegram_peer_id or channel.configured_reference

    @staticmethod
    def _to_post(message: Any) -> TelegramPost:
        media: list[dict[str, Any]] = []
        if message.media:
            media.append({"kind": type(message.media).__name__})
        return TelegramPost(
            message_id=message.id,
            published_at=message.date,
            content=message.message or "",
            edited_at=message.edit_date,
            metadata={
                "grouped_id": message.grouped_id,
                "reply_to_message_id": getattr(message.reply_to, "reply_to_msg_id", None),
                "forward": bool(message.fwd_from),
                "views": message.views,
            },
            attachments=media,
        )
