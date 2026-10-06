"""Cross-boundary contract test: the scraper's gateway client against the real gateway app.

The two services are deployed separately and do not share a package, so this test is what keeps
their mirrored wire models compatible.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from telegram_monitor_gateway.api import create_app
from telegram_monitor_gateway.contract import (
    ChannelAvatar,
    ChannelFetchRequest,
    ChannelFetchResponse,
    ChannelPost,
)
from telegram_monitor_gateway.settings import GatewaySettings
from telegram_monitor_gateway.telegram import TelegramRateLimitedError
from telegram_monitor_scraper.gateway_client import GatewayChannelClient
from telegram_monitor_scraper.models import (
    BackfillWindow,
    GatewayRateLimitedError,
    MonitoredChannel,
)
from telegram_monitor_scraper.models import ChannelFetchRequest as ScraperRequest

TOKEN = "t" * 32
PUBLISHED = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)


class RecordingReader:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.requests: list[ChannelFetchRequest] = []

    async def fetch(self, request: ChannelFetchRequest) -> ChannelFetchResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        post = ChannelPost(
            message_id=11,
            published_at=PUBLISHED,
            content="text",
            edited_at=PUBLISHED + timedelta(minutes=5),
            metadata={"views": 9, "forward": False},
            attachments=[{"kind": "MessageMediaPhoto"}],
        )
        return ChannelFetchResponse(
            peer_id=123,
            username="example",
            title="Example",
            avatar=ChannelAvatar(content_type="image/jpeg", content_base64="/9j/"),
            newer_posts=[post],
            newer_complete=True,
            older_posts=[post],
            backfill_complete=False,
        )


def scraper_client(reader: RecordingReader) -> GatewayChannelClient:
    app = create_app(
        GatewaySettings(
            telegram_api_id=1,
            telegram_api_hash="hash",
            telegram_session_string="session",
            telegram_gateway_token=TOKEN,
        ),
        reader,
    )
    http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://gateway",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    return GatewayChannelClient(http, page_size=75)


async def test_scraper_requests_round_trip_through_the_gateway() -> None:
    reader = RecordingReader()
    cutoff = datetime(2025, 10, 1, tzinfo=UTC)

    result = await scraper_client(reader).fetch(
        MonitoredChannel(3, "example", 123, "public"),
        ScraperRequest(
            live_after_message_id=10,
            backfill=BackfillWindow(before_message_id=50, not_before=cutoff),
            include_avatar=True,
        ),
    )

    sent = reader.requests[0]
    assert sent.channel.configured_reference == "example"
    assert sent.channel.telegram_peer_id == 123
    assert sent.live_after_message_id == 10
    assert sent.backfill is not None
    assert sent.backfill.before_message_id == 50
    assert sent.backfill.not_before == cutoff
    assert sent.page_size == 75
    assert result.peer_id == 123
    assert result.avatar is not None
    assert result.avatar.content == b"\xff\xd8\xff"
    assert result.newer_posts[0].published_at == PUBLISHED
    assert result.newer_posts[0].edited_at == PUBLISHED + timedelta(minutes=5)
    assert result.older_posts[0].attachments == [{"kind": "MessageMediaPhoto"}]
    assert result.backfill_complete is False


async def test_new_channel_request_without_cursors_is_accepted() -> None:
    reader = RecordingReader()

    await scraper_client(reader).fetch(
        MonitoredChannel(3, "example", None, "public"),
        ScraperRequest(live_after_message_id=None, backfill=None, include_avatar=False),
    )

    assert reader.requests[0].live_after_message_id is None
    assert reader.requests[0].backfill is None
    assert reader.requests[0].include_avatar is False


async def test_gateway_rate_limit_reaches_the_scraper() -> None:
    with pytest.raises(GatewayRateLimitedError) as raised:
        await scraper_client(RecordingReader(TelegramRateLimitedError(120))).fetch(
            MonitoredChannel(3, "example", None, "public"),
            ScraperRequest(live_after_message_id=1, backfill=None, include_avatar=False),
        )

    assert raised.value.retry_after_seconds == 120
