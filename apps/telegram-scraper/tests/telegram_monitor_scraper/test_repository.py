"""Repository unit tests with a lightweight asyncpg-shaped fake."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from telegram_monitor_scraper.models import MonitoredChannel, TelegramPost
from telegram_monitor_scraper.repository import CollectionRepository


class FakeConnection:
    def __init__(self, latest: dict[str, object] | None = None) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.values = iter([1, 1, 2])
        self.latest = latest

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        yield

    async def fetchval(self, query: str, *args: object) -> int:
        return next(self.values)

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        return self.latest

    async def fetch(self, query: str, *args: object) -> list[dict[str, str]]:
        return [
            {
                "entity_id": "1",
                "alias": "text",
                "coarse_type": "organization",
                "monitored": "true",
            }
        ]

    async def execute(self, query: str, *args: object) -> None:
        self.executed.append((query, args))


class FakePool:
    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str) -> list[dict[str, object]]:
        return [
            {
                "id": 1,
                "configured_reference": "source",
                "telegram_peer_id": 2,
                "access_kind": "public",
            }
        ]

    async def fetchval(self, query: str, *args: object) -> object:
        if "backfill_before" in query:
            return 4
        if "backfill_completed" in query:
            return True
        if "published_at <" in query:
            return 2
        return 3

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[FakeConnection]:
        yield self.connection

    async def execute(self, query: str, *args: object) -> None:
        self.executed.append((query, args))


async def test_repository_persists_evidence_and_text_analysis_job() -> None:
    pool = FakePool()
    repository = CollectionRepository(pool)  # type: ignore[arg-type]
    channel = (await repository.active_channels())[0]
    post = TelegramPost(3, datetime.now(UTC), "text", None, {}, [])

    assert channel == MonitoredChannel(1, "source", 2, "public")
    assert await repository.latest_message_id(1) == 3
    assert await repository.live_cursor_exists(1) is True
    assert await repository.backfill_before_message_id(1) == 4
    assert await repository.backfill_complete(1) is True
    assert await repository.refresh_anchor_message_id(1, datetime.now(UTC)) == 2
    assert await repository.persist_post(channel, post, "live") is True
    assert len(pool.connection.executed) == 1
    assert "INSERT INTO analysis_jobs" in pool.connection.executed[0][0]


async def test_repository_records_collection_health_and_deletion() -> None:
    pool = FakePool()
    repository = CollectionRepository(pool)  # type: ignore[arg-type]

    await repository.update_channel_identity(1, 2, "source", "Source")
    await repository.update_channel_avatar(1, "image/jpeg")
    await repository.clear_channel_avatar(1)
    await repository.advance_live_cursor(1, 3)
    await repository.advance_backfill_cursor(1, 2, complete=False)
    await repository.record_success(1)
    await repository.record_error(1, "failure")
    await repository.mark_deleted(1, [3])

    assert len(pool.executed) == 8


async def test_repository_skips_analysis_when_only_edit_metadata_changed() -> None:
    pool = FakePool()
    pool.connection = FakeConnection({"id": 7, "content": "text", "edited_at": None})
    repository = CollectionRepository(pool)  # type: ignore[arg-type]
    channel = (await repository.active_channels())[0]
    edited = TelegramPost(3, datetime.now(UTC), "text", datetime.now(UTC), {}, [])

    assert await repository.persist_post(channel, edited, "live") is True
    assert pool.connection.executed == []


async def test_repository_unchanged_post_creates_no_revision() -> None:
    pool = FakePool()
    pool.connection = FakeConnection({"id": 7, "content": "text", "edited_at": None})
    repository = CollectionRepository(pool)  # type: ignore[arg-type]
    channel = (await repository.active_channels())[0]
    same = TelegramPost(3, datetime.now(UTC), "text", None, {"forward": False}, [])

    assert await repository.persist_post(channel, same, "live") is False
