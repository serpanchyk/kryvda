"""HTTP wire contract between the department-hosted scraper and the Telegram gateway.

The gateway is deployed independently on Vercel, so it does not import workspace packages. The
scraper keeps a mirror of these models; a cross-boundary test exercises both sides together.
"""

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

AccessKind = Literal["public", "private"]
MAX_PAGE_SIZE = 500


class GatewayChannel(BaseModel):
    """Identify one monitored source without exposing the scraper's database identifiers."""

    model_config = ConfigDict(extra="forbid")

    configured_reference: str = Field(min_length=1)
    telegram_peer_id: int | None = None
    access_kind: AccessKind


class BackfillWindow(BaseModel):
    """Request one page of history older than a message ID and newer than a cutoff."""

    model_config = ConfigDict(extra="forbid")

    before_message_id: int | None = Field(default=None, ge=1)
    not_before: AwareDatetime


class ChannelFetchRequest(BaseModel):
    """Ask for current channel identity plus bounded live and historical post pages."""

    model_config = ConfigDict(extra="forbid")

    channel: GatewayChannel
    live_after_message_id: int | None = Field(default=None, ge=0)
    backfill: BackfillWindow | None = None
    page_size: int = Field(default=200, ge=1, le=MAX_PAGE_SIZE)
    include_avatar: bool = True


class ChannelPost(BaseModel):
    """A normalized Telegram channel message."""

    message_id: int
    published_at: AwareDatetime
    content: str
    edited_at: AwareDatetime | None
    metadata: dict[str, Any]
    attachments: list[dict[str, Any]]


class ChannelAvatar(BaseModel):
    """A channel's current profile image encoded for JSON transport."""

    content_type: str
    content_base64: str


class ChannelFetchResponse(BaseModel):
    """Collected channel state for one request.

    ``head_message_id`` is set only when the request had no live cursor. ``avatar`` and
    ``avatar_error`` are meaningful only when the request included the avatar.
    """

    peer_id: int
    username: str | None
    title: str | None
    avatar: ChannelAvatar | None = None
    avatar_error: str | None = None
    head_message_id: int | None = None
    newer_posts: list[ChannelPost] = Field(default_factory=list)
    newer_complete: bool = True
    older_posts: list[ChannelPost] = Field(default_factory=list)
    backfill_complete: bool = True
