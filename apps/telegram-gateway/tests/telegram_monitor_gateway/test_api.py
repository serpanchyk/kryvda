"""Gateway HTTP boundary tests with a fake Telegram reader."""

import asyncio

import httpx
import pytest
from telegram_monitor_gateway.api import create_app
from telegram_monitor_gateway.contract import ChannelFetchRequest, ChannelFetchResponse
from telegram_monitor_gateway.settings import GatewaySettings
from telegram_monitor_gateway.telegram import SessionNotAuthorizedError, TelegramRateLimitedError

TOKEN = "t" * 32
BODY = {"channel": {"configured_reference": "example", "access_kind": "public"}}


def settings() -> GatewaySettings:
    return GatewaySettings(
        telegram_api_id=1,
        telegram_api_hash="hash",
        telegram_session_string="session",
        telegram_gateway_token=TOKEN,
    )


class FakeReader:
    def __init__(self, error: Exception | None = None, delay: float = 0) -> None:
        self.error = error
        self.delay = delay
        self.active = 0
        self.max_active = 0

    async def fetch(self, request: ChannelFetchRequest) -> ChannelFetchResponse:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delay)
            if self.error is not None:
                raise self.error
            return ChannelFetchResponse(peer_id=1, username="example", title="Example")
        finally:
            self.active -= 1


def client_for(reader: FakeReader) -> httpx.AsyncClient:
    app = create_app(settings(), reader)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway")


async def test_health_needs_no_token() -> None:
    async with client_for(FakeReader()) as client:
        response = await client.get("/health")

    assert response.json() == {"status": "ok", "service": "telegram-monitor-gateway"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
async def test_fetch_requires_the_shared_token(headers: dict[str, str]) -> None:
    async with client_for(FakeReader()) as client:
        response = await client.post("/v1/channels/fetch", json=BODY, headers=headers)

    assert response.status_code == 401


async def test_fetch_returns_reader_response() -> None:
    async with client_for(FakeReader()) as client:
        response = await client.post(
            "/v1/channels/fetch", json=BODY, headers={"Authorization": f"Bearer {TOKEN}"}
        )

    assert response.status_code == 200
    assert response.json()["peer_id"] == 1


async def test_invalid_request_is_rejected() -> None:
    async with client_for(FakeReader()) as client:
        response = await client.post(
            "/v1/channels/fetch",
            json={**BODY, "page_size": 10_000},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (TelegramRateLimitedError(600), 429, "Telegram flood wait of 600 seconds"),
        (SessionNotAuthorizedError("revoked"), 503, "revoked"),
        (ValueError("absent"), 502, "ValueError: absent"),
    ],
)
async def test_errors_are_mapped_to_http_statuses(
    error: Exception, status_code: int, detail: str
) -> None:
    async with client_for(FakeReader(error)) as client:
        response = await client.post(
            "/v1/channels/fetch", json=BODY, headers={"Authorization": f"Bearer {TOKEN}"}
        )

    assert response.status_code == status_code
    assert response.json()["detail"] == detail
    if status_code == 429:
        assert response.headers["Retry-After"] == "600"


async def test_concurrent_requests_never_share_the_session() -> None:
    reader = FakeReader(delay=0.01)
    async with client_for(reader) as client:
        responses = await asyncio.gather(
            *(
                client.post(
                    "/v1/channels/fetch", json=BODY, headers={"Authorization": f"Bearer {TOKEN}"}
                )
                for _ in range(3)
            )
        )

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert reader.max_active == 1


def test_short_gateway_token_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 32"):
        GatewaySettings(
            telegram_api_id=1,
            telegram_api_hash="hash",
            telegram_session_string="session",
            telegram_gateway_token="short",
        )
