"""Repository tests for registry review and historical backfill."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from telegram_monitor_api.registry import RegistryRepository, _unique_aliases


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.next_job = 100

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        yield

    async def execute(self, query: str, *args: object) -> None:
        self.executed.append((query, args))

    async def fetchval(self, query: str, *args: object) -> object:
        self.executed.append((query, args))
        if "INSERT INTO registry_entities" in query:
            return 4
        if "INSERT INTO analysis_jobs" in query:
            self.next_job += 1
            return self.next_job
        if "UPDATE candidate_entities" in query:
            return 8
        if "UPDATE entity_alias_candidates" in query:
            return 9
        if "SELECT monitored" in query:
            return True
        if "SELECT EXISTS" in query:
            return True
        return 1

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        self.executed.append((query, args))
        if "candidate.surface_form" in query:
            return {"entity_id": 4, "surface_form": "Шабунін", "monitored": True}
        if "SELECT monitored" in query:
            return {"monitored": False}
        if "FROM registry_entities" in query:
            return {"monitored": True}
        return None

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        self.executed.append((query, args))
        if "DISTINCT ON" in query:
            return [
                {"id": 11, "content": "Шабунін згаданий."},
                {"id": 12, "content": "Інший пост."},
            ]
        if "JOIN entity_aliases" in query:
            return [
                {
                    "entity_id": 4,
                    "alias": "Шабунін",
                    "coarse_type": "person",
                    "monitored": True,
                }
            ]
        return []


class FakePool:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[FakeConnection]:
        yield self.connection

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        if "mention_count" in query:
            return [{"id": 4, "canonical_name": "Шабунін", "mention_count": 1}]
        if "candidate_entities" in query:
            return [{"id": 8, "status": args[0]}]
        return [{"id": 9, "surface_form": "Шабунін"}]

    async def fetchval(self, query: str, *args: object) -> object:
        return await self.connection.fetchval(query, *args)


async def test_create_entity_deduplicates_aliases_and_enqueues_matches() -> None:
    pool = FakePool()
    repository = RegistryRepository(pool)  # type: ignore[arg-type]

    entity_id, jobs = await repository.create_entity(
        "Віталій Шабунін", "person", ["Шабунін", "ШАБУНІН"], True
    )

    assert (entity_id, jobs) == (4, 1)
    alias_inserts = [
        args for query, args in pool.connection.executed if "INSERT INTO entity_aliases" in query
    ]
    assert len(alias_inserts) == 2
    assert _unique_aliases("Шабунін", [" Шабунін ", "Шабунін"]) == ["Шабунін"]


async def test_registry_lists_updates_links_and_reviews_candidates() -> None:
    pool = FakePool()
    repository = RegistryRepository(pool)  # type: ignore[arg-type]

    page = await repository.list_entities(None, None, None, None, None, "name", 25, 0)
    assert page["items"][0]["id"] == 4
    assert (await repository.list_candidates("pending"))[0]["id"] == 8
    assert (await repository.list_alias_candidates(4))[0]["id"] == 9
    assert await repository.update_entity(4, None, None, True) == 1
    assert await repository.add_alias(4, "Шабунін") == 1
    assert await repository.link_candidate(8, 4) == 0
    assert await repository.ignore_candidate(8) is True
    assert await repository.review_alias_candidate(9, True) == 1
    assert await repository.review_alias_candidate(9, False) == 0
