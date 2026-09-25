"""Focused tests for editorial analytics response assembly."""

from typing import Any

from telegram_monitor_api.analytics import (
    _CHANNEL_ATTRIBUTION_SQL,
    _CHANNEL_DAILY_SQL,
    _CHANNEL_ENTITY_COUNT_SQL,
    _CHANNEL_ENTITY_PAGE_SQL,
    _CHANNEL_EPISTEMIC_SQL,
    _CHANNEL_INCOMPLETE_SQL,
    _CHANNEL_RHETORIC_SQL,
    _CHANNEL_SQL,
    _CHANNEL_TOTAL_SQL,
    _CLAIMS_COUNT_SQL,
    AnalyticsRepository,
)


class EditorialPool:
    """Return deterministic rows for the channel-profile query sequence."""

    calls: list[tuple[str, tuple[object, ...]]]

    def __init__(self) -> None:
        self.calls = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        self.calls.append((query, args))
        if query == _CHANNEL_SQL:
            return {"id": args[0], "title": "Канал", "username": "channel"}
        if query == _CHANNEL_TOTAL_SQL:
            return {
                "post_count": 4,
                "claim_count": 7,
                "entity_count": 2,
                "positive_count": 1,
                "negative_count": 3,
                "absent_count": 3,
            }
        return None

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        self.calls.append((query, args))
        if query == _CHANNEL_DAILY_SQL:
            return [{"date": "2026-09-01", "negative_count": 3}]
        if query == _CHANNEL_ENTITY_PAGE_SQL:
            return [{"id": 4, "canonical_name": "Сутність", "negative_count": 3}]
        if query in {_CHANNEL_RHETORIC_SQL, _CHANNEL_EPISTEMIC_SQL, _CHANNEL_ATTRIBUTION_SQL}:
            return [{"key": "category", "count": 3, "share": 1.0}]
        return []

    async def fetchval(self, query: str, *args: object) -> int:
        self.calls.append((query, args))
        if query == _CHANNEL_ENTITY_COUNT_SQL:
            return 2
        if query == _CHANNEL_INCOMPLETE_SQL:
            return 1
        if query == _CLAIMS_COUNT_SQL:
            return 0
        return 0


async def test_channel_profile_assembles_editorial_distributions() -> None:
    pool = EditorialPool()
    result = await AnalyticsRepository(pool).channel(2, None, None, 25, 0)  # type: ignore[arg-type]

    assert result is not None
    assert result["channel"]["title"] == "Канал"
    assert result["summary"]["negative_count"] == 3
    assert result["entities"] == {
        "items": [{"id": 4, "canonical_name": "Сутність", "negative_count": 3}],
        "total": 2,
        "limit": 25,
        "offset": 0,
    }
    assert result["rhetoric"] == [{"key": "category", "count": 3, "share": 1.0}]
    assert result["epistemic"] == [{"key": "category", "count": 3, "share": 1.0}]
    assert result["attribution"] == [{"key": "category", "count": 3, "share": 1.0}]
    assert result["incomplete_posts"] == 1


async def test_channel_profile_returns_none_for_unknown_channel() -> None:
    pool = EditorialPool()

    async def missing(_: str, *args: object) -> None:
        pool.calls.append(("missing", args))
        return None

    pool.fetchrow = missing  # type: ignore[method-assign]
    assert await AnalyticsRepository(pool).channel(404, None, None, 25, 0) is None  # type: ignore[arg-type]


class JsonPool:
    """Mimic asyncpg's default JSONB text decoding."""

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        return {"id": args[0], "claims": '[{"id": 1, "rhetoric": ["делегітимізація"]}]'}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        return [{"claim_id": 1, "rhetoric": '["делегітимізація"]'}]

    async def fetchval(self, query: str, *args: object) -> int:
        return 1


async def test_jsonb_claim_fields_are_normalized_for_http_clients() -> None:
    repository = AnalyticsRepository(JsonPool())  # type: ignore[arg-type]

    post = await repository.post(9)
    claims = await repository.claims(
        None, None, None, None, None, None, None, None, None, "newest", 25, 0
    )

    assert post is not None
    assert post["claims"] == [{"id": 1, "rhetoric": ["делегітимізація"]}]
    assert claims["items"][0]["rhetoric"] == ["делегітимізація"]
