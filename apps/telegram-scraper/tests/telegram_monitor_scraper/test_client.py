"""Telethon adapter normalization tests."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

from telegram_monitor_scraper.client import TelethonChannelClient
from telegram_monitor_scraper.models import MonitoredChannel


class FakeTelegramClient:
    """Capture the Telethon arguments used by the adapter."""

    def __init__(self) -> None:
        self.iter_messages_calls: list[tuple[object, dict[str, Any]]] = []
        self.messages: list[Any] = []

    async def get_entity(self, reference: int | str) -> object:
        return reference

    async def get_messages(self, entity: object, limit: int) -> list[SimpleNamespace]:
        return [SimpleNamespace(id=73)]

    async def iter_messages(self, entity: object, **kwargs: Any) -> AsyncIterator[Any]:
        self.iter_messages_calls.append((entity, kwargs))
        for message in self.messages:
            yield message


def test_message_is_normalized_without_downloading_media() -> None:
    message = SimpleNamespace(
        id=10,
        date=datetime.now(UTC),
        message="caption",
        edit_date=None,
        grouped_id=None,
        reply_to=None,
        fwd_from=None,
        views=3,
        media=SimpleNamespace(),
    )

    post = TelethonChannelClient._to_post(message)

    assert post.content == "caption"
    assert post.metadata["views"] == 3
    assert post.attachments == [{"kind": "SimpleNamespace"}]


async def test_first_backfill_omits_telethon_max_id() -> None:
    fake_client = FakeTelegramClient()
    client = TelethonChannelClient.__new__(TelethonChannelClient)
    client._client = cast(Any, fake_client)
    channel = MonitoredChannel(1, "example_channel", 123, "public")

    async for _ in client.older_posts(channel, before_message_id=None):
        pass

    assert fake_client.iter_messages_calls == [("example_channel", {})]


async def test_newest_message_id_uses_the_channel_head() -> None:
    fake_client = FakeTelegramClient()
    client = TelethonChannelClient.__new__(TelethonChannelClient)
    client._client = cast(Any, fake_client)
    channel = MonitoredChannel(1, "example_channel", None, "public")

    assert await client.newest_message_id(channel) == 73


async def test_backfill_normalizes_messages_after_the_initial_request() -> None:
    fake_client = FakeTelegramClient()
    fake_client.messages = [
        SimpleNamespace(
            id=10,
            date=datetime.now(UTC),
            message="historical post",
            edit_date=None,
            grouped_id=None,
            reply_to=None,
            fwd_from=None,
            views=3,
            media=None,
        )
    ]
    client = TelethonChannelClient.__new__(TelethonChannelClient)
    client._client = cast(Any, fake_client)
    channel = MonitoredChannel(1, "example_channel", None, "public")

    posts = [post async for post in client.older_posts(channel, before_message_id=None)]

    assert [post.message_id for post in posts] == [10]
