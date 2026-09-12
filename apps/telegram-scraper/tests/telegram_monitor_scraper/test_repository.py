"""Repository unit tests with a lightweight asyncpg-shaped fake."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from telegram_monitor_scraper.models import MonitoredChannel, TelegramPost
from telegram_monitor_scraper.repository import CollectionRepository


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.values = iter([1, 1, 2])

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        yield

    async def fetchval(self, query: str, *args: object) -> int:
        return next(self.values)

    async def fetchrow(self, query: str, *args: object) -> None:
        return None

    async def fetch(self, query: str, *args: object) -> list[dict[str, str]]:
        return [{"alias": "text"}]

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
