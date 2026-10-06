"""Telegram gateway HTTP client tests against an in-memory transport."""

import base64
import json
from datetime import UTC, datetime

import httpx
import pytest
from telegram_monitor_scraper.gateway_client import GatewayChannelClient, GatewayError
from telegram_monitor_scraper.models import (
    BackfillWindow,
    ChannelFetchRequest,
    GatewayRateLimitedError,
    MonitoredChannel,
)

CHANNEL = MonitoredChannel(7, "private:123", 123, "private")
REQUEST = ChannelFetchRequest(
    live_after_message_id=5,
    backfill=BackfillWindow(40, datetime(2025, 10, 1, tzinfo=UTC)),
    include_avatar=True,
)


def client_for(handler: httpx.MockTransport) -> GatewayChannelClient:
    return GatewayChannelClient(
        httpx.AsyncClient(base_url="https://gateway.test", transport=handler), page_size=50
    )


async def test_fetch_sends_cursors_and_parses_posts_and_avatar() -> None:
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "peer_id": 123,
                "username": None,
                "title": "Private",
                "avatar": {
                    "content_type": "image/png",
                    "content_base64": base64.b64encode(b"\x89PNG").decode(),
                },
                "newer_posts": [
                    {
                        "message_id": 6,
                        "published_at": "2026-10-01T10:00:00Z",
                        "content": "text",
                        "edited_at": None,
                        "metadata": {"views": 3},
                        "attachments": [],
                    }
                ],
                "newer_complete": True,
                "older_posts": [],
                "backfill_complete": False,
            },
        )

    result = await client_for(httpx.MockTransport(handle)).fetch(CHANNEL, REQUEST)

    body = json.loads(captured[0].content)
    assert captured[0].url.path == "/v1/channels/fetch"
    assert body == {
        "channel": {
            "configured_reference": "private:123",
            "telegram_peer_id": 123,
            "access_kind": "private",
        },
        "live_after_message_id": 5,
        "backfill": {"before_message_id": 40, "not_before": "2025-10-01T00:00:00+00:00"},
        "page_size": 50,
        "include_avatar": True,
    }
    assert result.avatar is not None
    assert result.avatar.content == b"\x89PNG"
    assert result.newer_posts[0].message_id == 6
    assert result.newer_posts[0].published_at == datetime(2026, 10, 1, 10, tzinfo=UTC)
    assert result.backfill_complete is False


async def test_connect_sets_bearer_token_and_strips_trailing_slash() -> None:
    client = GatewayChannelClient.connect("https://gateway.test/", "secret", 12, 200)
    try:
        assert client._http.headers["Authorization"] == "Bearer secret"
        assert str(client._http.base_url) == "https://gateway.test"
    finally:
        await client.aclose()


async def test_rate_limit_carries_retry_after() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            429,
            json={"detail": "Telegram flood wait of 600 seconds"},
            headers={"Retry-After": "600"},
        )
    )

    with pytest.raises(GatewayRateLimitedError) as raised:
        await client_for(transport).fetch(CHANNEL, REQUEST)

    assert raised.value.retry_after_seconds == 600
    assert "600 seconds" in str(raised.value)


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(502, json={"detail": "ValueError: absent"}), "502: ValueError: absent"),
        (httpx.Response(500, text="Internal Server Error"), "500: Internal Server Error"),
        (httpx.Response(200, json={"unexpected": True}), "invalid response"),
    ],
)
async def test_gateway_failures_are_reported(response: httpx.Response, message: str) -> None:
    with pytest.raises(GatewayError, match=message):
        await client_for(httpx.MockTransport(lambda _: response)).fetch(CHANNEL, REQUEST)


async def test_unreachable_gateway_is_reported() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(GatewayError, match="unreachable"):
        await client_for(httpx.MockTransport(refuse)).fetch(CHANNEL, REQUEST)
