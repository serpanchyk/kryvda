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
