"""Telethon adapter tests with an in-memory Telegram client."""

import base64
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from telegram_monitor_gateway.contract import (
    BackfillWindow,
    ChannelFetchRequest,
    GatewayChannel,
)
from telegram_monitor_gateway.settings import GatewaySettings
from telegram_monitor_gateway.telegram import (
    SessionNotAuthorizedError,
    TelegramChannelReader,
    TelegramRateLimitedError,
)
from telethon.errors import FloodWaitError

PUBLIC = GatewayChannel(configured_reference="example_channel", access_kind="public")


def message(message_id: int, days_old: int = 0, **overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "id": message_id,
        "date": datetime.now(UTC) - timedelta(days=days_old),
        "message": f"post {message_id}",
        "edit_date": None,
        "grouped_id": None,
        "reply_to": None,
        "fwd_from": None,
        "views": 3,
        "media": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeTelegramClient:
    """Capture the Telethon calls made by the reader."""

    def __init__(self, messages: list[SimpleNamespace] | None = None) -> None:
        self.messages = sorted(messages or [], key=lambda item: item.id)
        self.authorized = True
        self.avatar: object = None
        self.avatar_error: Exception | None = None
        self.dialogs: list[SimpleNamespace] = []
        self.iter_calls: list[dict[str, Any]] = []
        self.connected = False
        self.disconnected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def is_user_authorized(self) -> bool:
        return self.authorized

    async def get_entity(self, reference: str) -> SimpleNamespace:
        return SimpleNamespace(id=55, username=reference, title="Example")

    async def get_dialogs(self) -> list[SimpleNamespace]:
        return self.dialogs

    async def get_messages(self, entity: object, limit: int) -> list[SimpleNamespace]:
        return self.messages[-limit:][::-1]

    async def download_profile_photo(self, entity: object, file: type[bytes]) -> object:
        if self.avatar_error is not None:
            raise self.avatar_error
        return self.avatar

    async def iter_messages(self, entity: object, **kwargs: Any) -> AsyncIterator[SimpleNamespace]:
        self.iter_calls.append(kwargs)
        if kwargs.get("reverse"):
            selected = [m for m in self.messages if m.id > kwargs["min_id"]]
        else:
            selected = [m for m in self.messages[::-1] if m.id < kwargs.get("max_id", 10**9)]
        for item in selected[: kwargs["limit"]]:
            yield item


def reader_for(client: FakeTelegramClient) -> TelegramChannelReader:
    return TelegramChannelReader(lambda: client)


async def test_new_channel_returns_head_avatar_and_closes_connection() -> None:
    client = FakeTelegramClient([message(70), message(73)])
    client.avatar = b"\xff\xd8\xffavatar"

    response = await reader_for(client).fetch(ChannelFetchRequest(channel=PUBLIC))

    assert (response.peer_id, response.username, response.title) == (
        55,
        "example_channel",
        "Example",
    )
    assert response.head_message_id == 73
    assert response.avatar is not None
    assert response.avatar.content_type == "image/jpeg"
    assert base64.b64decode(response.avatar.content_base64) == b"\xff\xd8\xffavatar"
    assert client.connected and client.disconnected


async def test_live_page_is_ascending_and_reports_more() -> None:
    client = FakeTelegramClient([message(message_id) for message_id in range(1, 6)])

    response = await reader_for(client).fetch(
        ChannelFetchRequest(
            channel=PUBLIC, live_after_message_id=2, page_size=2, include_avatar=False
        )
    )

    assert [post.message_id for post in response.newer_posts] == [3, 4]
    assert response.newer_complete is False
    assert response.head_message_id is None
    assert client.iter_calls == [{"min_id": 2, "reverse": True, "limit": 2}]


async def test_backfill_stops_at_cutoff_and_normalizes_messages() -> None:
    client = FakeTelegramClient(
        [
            message(8, days_old=400),
            message(
                9,
                media=SimpleNamespace(),
                fwd_from=object(),
                reply_to=SimpleNamespace(reply_to_msg_id=4),
            ),
            message(10),
        ]
    )

    response = await reader_for(client).fetch(
        ChannelFetchRequest(
            channel=PUBLIC,
            live_after_message_id=10,
            backfill=BackfillWindow(
                before_message_id=None, not_before=datetime.now(UTC) - timedelta(days=365)
            ),
            include_avatar=False,
        )
    )

    assert [post.message_id for post in response.older_posts] == [10, 9]
    assert response.backfill_complete is True
    assert response.older_posts[1].attachments == [{"kind": "SimpleNamespace"}]
    assert response.older_posts[1].metadata == {
        "grouped_id": None,
        "reply_to_message_id": 4,
        "forward": True,
        "views": 3,
    }
    assert client.iter_calls[-1] == {"limit": 200}


async def test_full_backfill_page_is_not_complete() -> None:
    client = FakeTelegramClient([message(message_id) for message_id in range(1, 6)])

    response = await reader_for(client).fetch(
        ChannelFetchRequest(
            channel=PUBLIC,
            live_after_message_id=5,
            backfill=BackfillWindow(
                before_message_id=5, not_before=datetime.now(UTC) - timedelta(days=365)
            ),
            page_size=2,
            include_avatar=False,
        )
    )

    assert [post.message_id for post in response.older_posts] == [4, 3]
    assert response.backfill_complete is False
    assert client.iter_calls[-1] == {"limit": 2, "max_id": 5}


async def test_private_channel_is_resolved_from_session_dialogs() -> None:
    client = FakeTelegramClient([message(1)])
    client.dialogs = [SimpleNamespace(entity=SimpleNamespace(id=123, title="Private"))]

    response = await reader_for(client).fetch(
        ChannelFetchRequest(
            channel=GatewayChannel(
                configured_reference="private:123", telegram_peer_id=123, access_kind="private"
            ),
            include_avatar=False,
        )
    )

    assert response.peer_id == 123
    assert response.username is None


async def test_private_channel_absent_from_dialogs_is_rejected() -> None:
    client = FakeTelegramClient()

    with pytest.raises(ValueError, match="absent from the session dialogs"):
        await reader_for(client).fetch(
            ChannelFetchRequest(
                channel=GatewayChannel(
                    configured_reference="private:9", telegram_peer_id=9, access_kind="private"
                )
            )
        )
    assert client.disconnected


@pytest.mark.parametrize(
    ("avatar", "error", "expected_error"),
    [
        (None, None, None),
        (b"unknown", None, "unsupported channel profile image format"),
        ("not-bytes", None, "non-bytes"),
        (None, RuntimeError("download failed"), "download failed"),
    ],
)
async def test_avatar_problems_do_not_fail_the_fetch(
    avatar: object, error: Exception | None, expected_error: str | None
) -> None:
    client = FakeTelegramClient()
    client.avatar = avatar
    client.avatar_error = error

    response = await reader_for(client).fetch(ChannelFetchRequest(channel=PUBLIC))

    assert response.avatar is None
    if expected_error is None:
        assert response.avatar_error is None
    else:
        assert response.avatar_error is not None
        assert expected_error in response.avatar_error


@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"\x89PNG\r\n\x1a\nrest", "image/png"),
        (b"GIF89a", "image/gif"),
        (b"RIFF\x00\x00\x00\x00WEBP", "image/webp"),
    ],
)
async def test_avatar_formats_are_detected(content: bytes, content_type: str) -> None:
    client = FakeTelegramClient()
    client.avatar = content

    response = await reader_for(client).fetch(ChannelFetchRequest(channel=PUBLIC))

    assert response.avatar is not None
    assert response.avatar.content_type == content_type


async def test_unauthorized_session_is_reported() -> None:
    client = FakeTelegramClient()
    client.authorized = False

    with pytest.raises(SessionNotAuthorizedError):
        await reader_for(client).fetch(ChannelFetchRequest(channel=PUBLIC))
    assert client.disconnected


async def test_long_flood_wait_becomes_rate_limit() -> None:
    class FloodedClient(FakeTelegramClient):
        async def get_entity(self, reference: str) -> SimpleNamespace:
            raise FloodWaitError(request=None, capture=600)

    client = FloodedClient()

    with pytest.raises(TelegramRateLimitedError) as raised:
        await reader_for(client).fetch(ChannelFetchRequest(channel=PUBLIC))

    assert raised.value.seconds == 600
    assert client.disconnected


def test_reader_from_settings_builds_an_unconnected_telethon_client() -> None:
    settings = GatewaySettings(
        telegram_api_id=1,
        telegram_api_hash="hash",
        telegram_session_string="",
        telegram_gateway_token="t" * 32,
    )
    reader = TelegramChannelReader.from_settings(settings)

    client = reader._client_factory()

    assert client.flood_sleep_threshold == 20
    assert not client.is_connected()
