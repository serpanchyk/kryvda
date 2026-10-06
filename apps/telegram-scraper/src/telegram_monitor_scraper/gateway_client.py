"""HTTP client for the Telegram gateway that runs outside the department firewall.

The wire models mirror ``telegram_monitor_gateway.contract``; the gateway is deployed separately
and cannot share a workspace package, so a cross-boundary test keeps both sides compatible.
"""

import base64
from typing import Any

import httpx
from pydantic import AwareDatetime, BaseModel

from telegram_monitor_scraper.models import (
    ChannelAvatar,
    ChannelFetchRequest,
    ChannelFetchResult,
    GatewayRateLimitedError,
    MonitoredChannel,
    TelegramPost,
)

FETCH_PATH = "/v1/channels/fetch"


class GatewayError(RuntimeError):
    """The gateway rejected a request or returned an unusable response."""


class _WirePost(BaseModel):
    message_id: int
    published_at: AwareDatetime
    content: str
    edited_at: AwareDatetime | None
    metadata: dict[str, Any]
    attachments: list[dict[str, Any]]


class _WireAvatar(BaseModel):
    content_type: str
    content_base64: str


class _WireFetchResponse(BaseModel):
    peer_id: int
    username: str | None
    title: str | None
    avatar: _WireAvatar | None = None
    avatar_error: str | None = None
    head_message_id: int | None = None
    newer_posts: list[_WirePost] = []
    newer_complete: bool = True
    older_posts: list[_WirePost] = []
    backfill_complete: bool = True


class GatewayChannelClient:
    """Fetch channel pages from the Telegram gateway.

    Args:
        http: Client configured with the gateway base URL, Bearer token, and timeout.
        page_size: Maximum live and historical posts requested per call.
    """

    def __init__(self, http: httpx.AsyncClient, page_size: int = 200) -> None:
        self._http = http
        self._page_size = page_size

    @classmethod
    def connect(
        cls, base_url: str, token: str, timeout_seconds: float, page_size: int
    ) -> "GatewayChannelClient":
        """Build a client for a deployed or local gateway.

        Args:
            base_url: Gateway origin, for example ``https://example.vercel.app``.
            token: Shared Bearer token configured on the gateway.
            timeout_seconds: Per-request timeout, longer than the gateway's own limit.
            page_size: Maximum posts requested per page.

        Returns:
            Ready gateway client; close it with :meth:`aclose`.
        """
        http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_seconds,
        )
        return cls(http, page_size)

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._http.aclose()

    async def fetch(
        self, channel: MonitoredChannel, request: ChannelFetchRequest
    ) -> ChannelFetchResult:
        """Request one bounded page of channel state.

        Args:
            channel: Monitored source to read.
            request: Live and historical cursors for this page.

        Returns:
            Channel identity, optional avatar, and post pages.

        Raises:
            GatewayRateLimitedError: If Telegram asked the gateway to wait.
            GatewayError: If the gateway failed or returned an invalid response.
        """
        payload = {
            "channel": {
                "configured_reference": channel.configured_reference,
                "telegram_peer_id": channel.telegram_peer_id,
                "access_kind": channel.access_kind,
            },
            "live_after_message_id": request.live_after_message_id,
            "backfill": None
            if request.backfill is None
            else {
                "before_message_id": request.backfill.before_message_id,
                "not_before": request.backfill.not_before.isoformat(),
            },
            "page_size": self._page_size,
            "include_avatar": request.include_avatar,
        }
        try:
            response = await self._http.post(FETCH_PATH, json=payload)
        except httpx.HTTPError as error:
            raise GatewayError(f"Telegram gateway is unreachable: {error!r}") from error
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            retry_after = response.headers.get("Retry-After")
            raise GatewayRateLimitedError(
                f"Telegram gateway rate limited: {self._detail(response)}",
                int(retry_after) if retry_after and retry_after.isdigit() else None,
            )
        if response.is_error:
            raise GatewayError(
                f"Telegram gateway returned {response.status_code}: {self._detail(response)}"
            )
        try:
            wire = _WireFetchResponse.model_validate_json(response.content)
        except ValueError as error:
            raise GatewayError(f"Telegram gateway returned an invalid response: {error}") from error
        return ChannelFetchResult(
            peer_id=wire.peer_id,
            username=wire.username,
            title=wire.title,
            avatar=None
            if wire.avatar is None
            else ChannelAvatar(
                base64.b64decode(wire.avatar.content_base64), wire.avatar.content_type
            ),
            avatar_error=wire.avatar_error,
            head_message_id=wire.head_message_id,
            newer_posts=[self._post(post) for post in wire.newer_posts],
            newer_complete=wire.newer_complete,
            older_posts=[self._post(post) for post in wire.older_posts],
            backfill_complete=wire.backfill_complete,
        )

    @staticmethod
    def _post(post: _WirePost) -> TelegramPost:
        return TelegramPost(
            message_id=post.message_id,
            published_at=post.published_at,
            content=post.content,
            edited_at=post.edited_at,
            metadata=post.metadata,
            attachments=post.attachments,
        )

    @staticmethod
    def _detail(response: httpx.Response) -> str:
        """Extract FastAPI's error detail, falling back to a bounded body excerpt."""
        try:
            body = response.json()
        except ValueError:
            return response.text[:500]
        if isinstance(body, dict) and "detail" in body:
            return str(body["detail"])
        return response.text[:500]
