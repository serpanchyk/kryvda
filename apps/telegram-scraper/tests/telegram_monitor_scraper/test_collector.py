"""Collection orchestration tests without a Telegram or PostgreSQL runtime."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from telegram_monitor_scraper.collector import Collector
from telegram_monitor_scraper.models import MonitoredChannel, TelegramPost


class FakeRepository:
    def __init__(self) -> None:
        self.channel = MonitoredChannel(1, "example_channel", 1, "public")
        self.live_cursor = 0
        self.backfill_cursor: int | None = None
        self.complete = False
        self.cursor_exists = True
        self.persisted: list[tuple[int, str]] = []
        self.identities: list[tuple[int, int, str | None, str | None]] = []

    async def active_channels(self) -> list[MonitoredChannel]:
        return [self.channel]

    async def latest_message_id(self, channel_id: int) -> int:
        return self.live_cursor

    async def live_cursor_exists(self, channel_id: int) -> bool:
        return self.cursor_exists

    async def update_channel_identity(
        self, channel_id: int, peer_id: int, username: str | None, title: str | None
    ) -> None:
        self.identities.append((channel_id, peer_id, username, title))

    async def backfill_before_message_id(self, channel_id: int) -> int | None:
        return self.backfill_cursor

    async def backfill_complete(self, channel_id: int) -> bool:
        return self.complete

    async def persist_post(
        self, channel: MonitoredChannel, post: TelegramPost, priority: str
    ) -> bool:
        self.persisted.append((post.message_id, priority))
        return True

    async def advance_live_cursor(self, channel_id: int, message_id: int) -> None:
        self.live_cursor = message_id

    async def advance_backfill_cursor(
        self, channel_id: int, message_id: int | None, complete: bool
    ) -> None:
        self.backfill_cursor = message_id
        self.complete = complete

    async def record_success(self, channel_id: int) -> None:
        return None

    async def record_error(self, channel_id: int, message: str) -> None:
        pytest.fail(message)


class FakeClient:
    def __init__(self, live: list[TelegramPost], historical: list[TelegramPost]) -> None:
        self.live = live
        self.historical = historical

    async def newer_posts(
        self, channel: MonitoredChannel, minimum_message_id: int
    ) -> AsyncIterator[TelegramPost]:
        for post in self.live:
            if post.message_id > minimum_message_id:
                yield post

    async def older_posts(
        self, channel: MonitoredChannel, before_message_id: int | None
    ) -> AsyncIterator[TelegramPost]:
        for post in self.historical:
            yield post

    async def newest_message_id(self, channel: MonitoredChannel) -> int:
        return 100

    async def resolve(self, channel: MonitoredChannel) -> tuple[int, str | None, str | None]:
        return 1, "example_channel", "Example"


def post(message_id: int, days_old: int = 0) -> TelegramPost:
    return TelegramPost(
        message_id=message_id,
        published_at=datetime.now(UTC) - timedelta(days=days_old),
        content="content",
        edited_at=None,
        metadata={},
        attachments=[],
    )


async def test_live_posts_are_collected_before_backfill() -> None:
    repository = FakeRepository()
    collector = Collector(repository, FakeClient([post(20)], [post(10), post(9, 366)]))  # type: ignore[arg-type]

    await collector.collect_once()

    assert repository.persisted == [(20, "live"), (10, "backfill")]
    assert repository.identities == [(1, 1, "example_channel", "Example")]
    assert repository.complete is True
    assert repository.live_cursor == 20


async def test_new_channel_sets_live_cursor_before_collecting_history() -> None:
    repository = FakeRepository()
    repository.cursor_exists = False
    collector = Collector(repository, FakeClient([post(20)], [post(10), post(9, 366)]))  # type: ignore[arg-type]

    await collector.collect_once()

    assert repository.live_cursor == 100
    assert repository.persisted == [(10, "backfill")]
