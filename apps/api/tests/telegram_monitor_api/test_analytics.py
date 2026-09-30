"""Focused tests for editorial analytics response assembly."""

import re
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
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
    _ENTITY_CHANNEL_PAGE_SQL,
    _EVIDENCE_SQL,
    _SOURCE_ACTOR_COUNT_SQL,
    _SOURCE_ACTOR_PAGE_SQL,
    AnalyticsRepository,
    EntityAnalyticsFilters,
    _fill_daily,
    negative_balance_metrics,
)


class DashboardPool:
    """Reject unrendered SQL templates in the dashboard query sequence."""

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        assert "{" not in query
        return {}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "{" not in query
        return []


async def test_dashboard_renders_channel_summary_ordering() -> None:
    result = await AnalyticsRepository(DashboardPool()).dashboard(None, None)  # type: ignore[arg-type]

    assert result["channels"] == []


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
            return [{"date": date(2026, 9, 1), "negative_count": 3}]
        if query == _CHANNEL_ENTITY_PAGE_SQL.format(
            order=(
                "negative_count DESC, evaluative_count DESC, negative_count DESC, "
                "entity.canonical_name ASC"
            )
        ):
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

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        self.calls.append((query, args))
        return {"id": args[0], "claims": '[{"id": 1, "rhetoric": ["делегітимізація"]}]'}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.calls.append((query, args))
        return [{"claim_id": 1, "rhetoric": '["делегітимізація"]'}]

    async def fetchval(self, query: str, *args: object) -> int:
        self.calls.append((query, args))
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


def test_entity_channel_page_uses_new_filter_pagination_arguments() -> None:
    """Regression: date parameters must not be reused as pagination offsets."""
    assert "LIMIT $11 OFFSET $12" in _ENTITY_CHANNEL_PAGE_SQL


async def test_source_actors_force_named_attribution_and_forward_global_filters() -> None:
    pool = JsonPool()
    repository = AnalyticsRepository(pool)  # type: ignore[arg-type]
    filters = EntityAnalyticsFilters(
        channel_id=7,
        stance="негативне",
        rhetoric="делегітимізація",
        epistemic_status="питання",
        source_kind="external_unnamed",
        source_entity_id=99,
        attribution_mode="quoted_sources",
    )

    result = await repository.source_actors(4, filters, None, None, "Автор", 25, 0)

    assert result["total"] == 1
    page_call = next(args for query, args in pool.calls if query == _SOURCE_ACTOR_PAGE_SQL)
    count_call = next(args for query, args in pool.calls if query == _SOURCE_ACTOR_COUNT_SQL)
    assert page_call[:8] == (
        4,
        7,
        "негативне",
        "делегітимізація",
        "питання",
        "named_entity",
        None,
        "quoted_sources",
    )
    assert page_call[10:] == ("Автор", 25, 0)
    assert count_call[5:7] == ("named_entity", None)


def test_negative_balance_metrics_penalize_small_samples() -> None:
    assert negative_balance_metrics(0, 0) == {
        "evaluative_count": 0,
        "negative_share": 0.0,
        "negative_balance_score": 0.0,
    }
    one_negative = negative_balance_metrics(0, 1)
    assert one_negative["negative_share"] == 1.0
    assert (
        one_negative["negative_balance_score"]
        < negative_balance_metrics(0, 100)["negative_balance_score"]
    )
    assert negative_balance_metrics(5, 5)["negative_share"] == 0.5
    assert negative_balance_metrics(9, 1)["negative_balance_score"] < 0.1
    assert (
        negative_balance_metrics(1, 9)["negative_balance_score"]
        > negative_balance_metrics(5, 5)["negative_balance_score"]
    )


def test_evidence_query_exposes_target_identity_and_candidate_source_fallback() -> None:
    """Evidence cards can show their target and an unresolved named source."""
    assert "entity.id AS entity_id" in _EVIDENCE_SQL
    assert "entity.canonical_name AS entity_name" in _EVIDENCE_SQL
    assert (
        "COALESCE(source_registry.canonical_name, source_candidate.representative_mention)"
        in _EVIDENCE_SQL
    )


class PlaceholderCheckingPool:
    """Fail when a query receives a different number of arguments than its placeholders."""

    def __init__(self) -> None:
        self.queries = 0

    def _check(self, query: str, args: tuple[object, ...]) -> None:
        self.queries += 1
        placeholders = [int(value) for value in re.findall(r"\$(\d+)", query)]
        assert len(args) == max(placeholders, default=0), query

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        self._check(query, args)
        return {"id": 1, "title": "Канал", "canonical_name": "Сутність", "monitored": True}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self._check(query, args)
        return []

    async def fetchval(self, query: str, *args: object) -> int:
        self._check(query, args)
        return 0


async def test_every_repository_query_binds_all_of_its_placeholders() -> None:
    """Regression: the claims count query once received nine of its ten arguments."""
    pool = PlaceholderCheckingPool()
    repository = AnalyticsRepository(pool)  # type: ignore[arg-type]
    filters = EntityAnalyticsFilters(source_entity_id=3)
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 3, tzinfo=UTC)

    await repository.dashboard(start, end)
    await repository.channels(start, end, 25, 0)
    await repository.channel(1, start, end, 25, 0)
    await repository.entity(1, filters, start, end, 25, 0)
    await repository.evidence(1, filters, start, end, 25, 0)
    await repository.source_actors(1, filters, start, end, "Автор", 25, 0)
    claims = await repository.claims(
        "пошук", 1, 2, "негативне", None, None, None, start, end, "newest", 25, 0, 3
    )

    assert claims["total"] == 0
    assert pool.queries > 20


def _day(value: date, negative: int = 1) -> dict[str, object]:
    return {"date": value, "post_count": 1, "claim_count": 1, "negative_count": negative}


def test_fill_daily_inserts_zero_days_between_sparse_rows() -> None:
    start = datetime(2026, 8, 31, 21, tzinfo=UTC)  # Kyiv midnight, 1 September
    end = datetime(2026, 9, 4, 21, tzinfo=UTC)  # exclusive Kyiv midnight, 5 September

    days = _fill_daily([_day(date(2026, 9, 2)), _day(date(2026, 9, 4))], start, end)

    assert [item["date"] for item in days] == [date(2026, 9, value) for value in range(1, 5)]
    assert days[0] == {
        "date": date(2026, 9, 1),
        "post_count": 0,
        "claim_count": 0,
        "positive_count": 0,
        "negative_count": 0,
        **negative_balance_metrics(0, 0),
        "absent_count": 0,
    }
    assert days[1]["negative_count"] == 1


def test_fill_daily_without_bounds_spans_first_row_to_today() -> None:
    days = _fill_daily([_day(date(2026, 1, 1))], None, None)

    assert days[0]["date"] == date(2026, 1, 1)
    assert days[-1]["date"] == datetime.now(ZoneInfo("Europe/Kyiv")).date()
    assert len(days) == (days[-1]["date"] - date(2026, 1, 1)).days + 1


def test_fill_daily_returns_nothing_for_unbounded_empty_series() -> None:
    assert _fill_daily([], None, None) == []


@pytest.mark.parametrize(
    ("start", "expected_first"),
    [
        (datetime(2026, 9, 1, 20, 59, tzinfo=UTC), date(2026, 9, 1)),
        (datetime(2026, 9, 1, 21, 0, tzinfo=UTC), date(2026, 9, 2)),
        (datetime(2026, 9, 2, 0, 0), date(2026, 9, 2)),
    ],
)
def test_fill_daily_uses_kyiv_report_days(start: datetime, expected_first: date) -> None:
    end = datetime(2026, 9, 3, 21, tzinfo=UTC)

    days = _fill_daily([], start, end)

    assert days[0]["date"] == expected_first
    assert days[-1]["date"] == date(2026, 9, 3)
