"""Telethon adapter isolated from collection orchestration."""

from collections.abc import AsyncIterator
from typing import Any

from telethon import TelegramClient
from telethon.sessions import StringSession

from telegram_monitor_scraper.models import ChannelAvatar, MonitoredChannel, TelegramPost


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
        entity = await self._entity(channel)
        return int(entity.id), getattr(entity, "username", None), getattr(entity, "title", None)

    async def avatar(self, channel: MonitoredChannel) -> ChannelAvatar | None:
        """Download the channel's current profile image when Telegram provides one.

        Args:
            channel: Source whose current profile image will be retrieved.

        Returns:
            Current image payload and MIME type, or ``None`` without a profile image.
        """
        entity = await self._entity(channel)
        content = await self._client.download_profile_photo(entity, file=bytes)
        if content is None:
            return None
        if not isinstance(content, bytes):
            raise TypeError("Telegram returned a non-bytes channel profile image")
        return ChannelAvatar(content, self._content_type(content))

    async def newer_posts(
        self, channel: MonitoredChannel, minimum_message_id: int
    ) -> AsyncIterator[TelegramPost]:
        entity = await self._entity(channel)
        async for message in self._client.iter_messages(
            entity, min_id=minimum_message_id, reverse=True
        ):
            yield self._to_post(message)

    async def newest_message_id(self, channel: MonitoredChannel) -> int:
        """Return the current head without walking a channel's full history."""
        entity = await self._entity(channel)
        messages = await self._client.get_messages(entity, limit=1)
        return int(messages[0].id) if messages else 0

    async def older_posts(
        self, channel: MonitoredChannel, before_message_id: int | None
    ) -> AsyncIterator[TelegramPost]:
        entity = await self._entity(channel)
        kwargs = {} if before_message_id is None else {"max_id": before_message_id}
        async for message in self._client.iter_messages(entity, **kwargs):
            yield self._to_post(message)

    async def _entity(self, channel: MonitoredChannel) -> Any:
        """Resolve a monitored source, restoring private-channel access metadata when needed.

        Args:
            channel: Source whose Telegram entity will be fetched.

        Returns:
            A Telethon entity accepted by message and profile-photo operations.
        """
        if channel.access_kind == "public":
            return await self._client.get_entity(channel.configured_reference)
        if channel.telegram_peer_id is None:
            return await self._client.get_entity(channel.configured_reference)

        cached_entities: dict[int, Any] = getattr(self, "_private_entities", {})
        if entity := cached_entities.get(channel.telegram_peer_id):
            return entity

        for dialog in await self._client.get_dialogs():
            entity = dialog.entity
            if getattr(entity, "id", None) == channel.telegram_peer_id:
                cached_entities[channel.telegram_peer_id] = entity
                self._private_entities = cached_entities
                return entity
        raise ValueError(
            f"Private channel peer ID {channel.telegram_peer_id} is absent from the session dialogs"
        )

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

    @staticmethod
    def _content_type(content: bytes) -> str:
        """Detect the image MIME type required by the HTTP response.

        Args:
            content: Raw image payload returned by Telegram.

        Returns:
            MIME type for a supported profile-image format.

        Raises:
            ValueError: If Telegram returns an unsupported image format.
        """
        if content.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if content.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            return "image/webp"
        raise ValueError("Telegram returned an unsupported channel profile image format")
