"""Typed records exchanged inside the Telegram collection boundary."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class MonitoredChannel:
    """An approved Telegram channel read from the monitoring registry."""

    id: int
    configured_reference: str
    telegram_peer_id: int | None
    access_kind: str


@dataclass(frozen=True, slots=True)
class TelegramPost:
    """A normalized Telegram channel message captured by the adapter."""

    message_id: int
    published_at: datetime
    content: str
    edited_at: datetime | None
    metadata: dict[str, Any]
    attachments: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ChannelAvatar:
    """Represent a channel profile image returned by Telegram."""

    content: bytes
    content_type: str


@dataclass(frozen=True, slots=True)
class BackfillWindow:
    """One historical page request: posts older than a message and newer than a cutoff."""

    before_message_id: int | None
    not_before: datetime


@dataclass(frozen=True, slots=True)
class ChannelFetchRequest:
    """Cursor state sent to the Telegram gateway for one channel page."""

    live_after_message_id: int | None
    backfill: BackfillWindow | None
    include_avatar: bool


@dataclass(frozen=True, slots=True)
class ChannelFetchResult:
    """Channel state returned by the Telegram gateway for one page.

    ``head_message_id`` is set only when the request had no live cursor; ``avatar`` and
    ``avatar_error`` are meaningful only when the request included the avatar.
    """

    peer_id: int
    username: str | None
    title: str | None
    avatar: ChannelAvatar | None
    avatar_error: str | None
    head_message_id: int | None
    newer_posts: list[TelegramPost]
    newer_complete: bool
    older_posts: list[TelegramPost]
    backfill_complete: bool


class GatewayRateLimitedError(RuntimeError):
    """Telegram asked the gateway to wait; the current collection run must stop."""

    def __init__(self, message: str, retry_after_seconds: int | None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
