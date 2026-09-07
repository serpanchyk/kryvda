"""Telethon adapter normalization tests."""

from datetime import UTC, datetime
from types import SimpleNamespace

from telegram_monitor_scraper.client import TelethonChannelClient


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
