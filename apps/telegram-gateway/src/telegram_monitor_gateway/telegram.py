"""Telethon adapter that serves one bounded channel fetch per connection."""

import base64
from collections.abc import Callable
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

from telegram_monitor_gateway.contract import (
    ChannelAvatar,
    ChannelFetchRequest,
    ChannelFetchResponse,
    ChannelPost,
    GatewayChannel,
)
from telegram_monitor_gateway.settings import GatewaySettings


class SessionNotAuthorizedError(RuntimeError):
    """The configured Telegram session string is missing, revoked, or expired."""


class TelegramRateLimitedError(RuntimeError):
    """Telegram requested a wait longer than the gateway is allowed to sleep."""

    def __init__(self, seconds: int) -> None:
        super().__init__(f"Telegram flood wait of {seconds} seconds")
        self.seconds = seconds


class TelegramChannelReader:
    """Read channel identity, avatar, and post pages through an authorized user session.

    Each fetch opens and closes its own MTProto connection, so a frozen or recycled serverless
    instance never keeps a session connected in the background.

    Args:
        client_factory: Builds an unconnected Telethon-compatible client.
    """

    def __init__(self, client_factory: Callable[[], Any]) -> None:
        self._client_factory = client_factory

    @classmethod
    def from_settings(cls, settings: GatewaySettings) -> "TelegramChannelReader":
        """Build a reader backed by the configured string session.

        Args:
            settings: Gateway runtime settings.

        Returns:
            Reader that creates a fresh Telethon client per fetch.
        """
        return cls(
            lambda: TelegramClient(
                StringSession(settings.telegram_session_string.get_secret_value()),
                settings.telegram_api_id,
                settings.telegram_api_hash.get_secret_value(),
                flood_sleep_threshold=settings.telegram_flood_sleep_threshold_seconds,
                receive_updates=False,
            )
        )

    async def fetch(self, request: ChannelFetchRequest) -> ChannelFetchResponse:
        """Collect one bounded snapshot of a monitored channel.

        Args:
            request: Channel, cursors, and page size chosen by the scraper.

        Returns:
            Identity, optional avatar, and the requested live and historical pages.

        Raises:
            SessionNotAuthorizedError: If the session string no longer authorizes the account.
            TelegramRateLimitedError: If Telegram requires a long flood wait.
        """
        client = self._client_factory()
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise SessionNotAuthorizedError(
                    "Telegram session is not authorized; generate a new TELEGRAM_SESSION_STRING"
                )
            return await self._fetch(client, request)
        except FloodWaitError as error:
            raise TelegramRateLimitedError(int(error.seconds)) from error
        finally:
            await client.disconnect()

    async def _fetch(self, client: Any, request: ChannelFetchRequest) -> ChannelFetchResponse:
        entity = await self._entity(client, request.channel)
        response = ChannelFetchResponse(
            peer_id=int(entity.id),
            username=getattr(entity, "username", None),
            title=getattr(entity, "title", None),
        )
        if request.include_avatar:
            try:
                response.avatar = await self._avatar(client, entity)
            except FloodWaitError:
                raise
            except Exception as error:
                response.avatar_error = str(error)

        if request.live_after_message_id is None:
            messages = await client.get_messages(entity, limit=1)
            response.head_message_id = int(messages[0].id) if messages else 0
        else:
            response.newer_posts = [
                self._to_post(message)
                async for message in client.iter_messages(
                    entity,
                    min_id=request.live_after_message_id,
                    reverse=True,
                    limit=request.page_size,
                )
            ]
            response.newer_complete = len(response.newer_posts) < request.page_size

        if request.backfill is not None:
            kwargs: dict[str, Any] = {"limit": request.page_size}
            if request.backfill.before_message_id is not None:
                kwargs["max_id"] = request.backfill.before_message_id
            seen = 0
            reached_cutoff = False
            async for message in client.iter_messages(entity, **kwargs):
                seen += 1
                post = self._to_post(message)
                if post.published_at < request.backfill.not_before:
                    reached_cutoff = True
                    break
                response.older_posts.append(post)
            response.backfill_complete = reached_cutoff or seen < request.page_size
        return response

    @staticmethod
    async def _entity(client: Any, channel: GatewayChannel) -> Any:
        """Resolve a monitored source, restoring private-channel access metadata when needed.

        Args:
            client: Connected Telethon client.
            channel: Source whose Telegram entity will be fetched.

        Returns:
            A Telethon entity accepted by message and profile-photo operations.
        """
        if channel.access_kind == "public" or channel.telegram_peer_id is None:
            return await client.get_entity(channel.configured_reference)
        for dialog in await client.get_dialogs():
            entity = dialog.entity
            if getattr(entity, "id", None) == channel.telegram_peer_id:
                return entity
        raise ValueError(
            f"Private channel peer ID {channel.telegram_peer_id} is absent from the session dialogs"
        )

    @classmethod
    async def _avatar(cls, client: Any, entity: Any) -> ChannelAvatar | None:
        """Download the channel's current profile image when Telegram provides one."""
        content = await client.download_profile_photo(entity, file=bytes)
        if content is None:
            return None
        if not isinstance(content, bytes):
            raise TypeError("Telegram returned a non-bytes channel profile image")
        return ChannelAvatar(
            content_type=cls._content_type(content),
            content_base64=base64.b64encode(content).decode("ascii"),
        )

    @staticmethod
    def _to_post(message: Any) -> ChannelPost:
        media: list[dict[str, Any]] = []
        if message.media:
            media.append({"kind": type(message.media).__name__})
        return ChannelPost(
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
        """Detect the image MIME type required by the scraper's avatar storage.

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
