"""System-dynamics endpoint and shaping tests."""

from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from telegram_monitor_api import main, system
from telegram_monitor_api.main import create_app
from telegram_monitor_api.system import (
    SystemRepository,
    report_days,
    report_hours,
    shape_days,
    shape_funnel,
    shape_hours,
    shape_models,
    shape_passes,
    shape_totals,
)

# 2026-10-24 21:30 UTC is already 2026-10-25 00:30 in Kyiv (UTC+3, summer time).
NOW = datetime(2026, 10, 24, 21, 30, tzinfo=UTC)
FUNNEL = ("analysed", "matched", "with_claims", "evaluative", "negative")


class SystemPool:
    """Answer each system query with dict rows chosen by query content."""

    def __init__(self, empty: bool = False) -> None:
        self.empty = empty
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.calls.append((query, args))
        if "FROM monitored_channels" in query:
            return [{"id": 1, "title": "INSIDER UA"}, {"id": 2, "title": None}]
        if self.empty:
            return []
        if "UNION ALL" in query:
            return [
                {"date": date(2026, 10, 25), "collected_posts": 12, "published_posts": 10},
                {"date": date(2026, 10, 1), "collected_posts": 99, "published_posts": 99},
            ]
        if "date_trunc('hour'" in query:
            return [{"hour": datetime(2026, 10, 24, 20), "completed": 7, "failed": None}]
        if "FROM analysis_runs" in query and "filtered_out" in query:
            return [
                {
                    "date": date(2026, 10, 24),
                    "completed": 40,
                    "partial": 1,
                    "fallback": 2,
                    "failed": 3,
                    "filtered_out": 4,
                }
            ]
        if "FROM inference_pass_attempts" in query:
            return [
                {
                    "pass_name": "classification",
                    "attempts": 5,
                    "repairs": 1,
                    "invalid": 1,
                    "failed": 0,
                    "median_ms": 1200.0,
                    "p95_ms": 3100.5,
                    "median_completion_tokens": None,
                },
                {
                    "pass_name": "targets",
                    "attempts": 2,
                    "repairs": 0,
                    "invalid": 0,
                    "failed": 0,
                    "median_ms": 800.0,
                    "p95_ms": 900.0,
                    "median_completion_tokens": 40.0,
                },
            ]
        if "GROUP BY model_name" in query:
            return [
                {
                    "model_name": "MamayLM",
                    "pipeline_version": "inference_v3_6",
                    "runs": 9,
                    "last_used_at": datetime(2026, 10, 24, 21, 0, tzinfo=UTC),
                }
            ]
        if "channel_id" in query:
            return [{"channel_id": 1, "date": date(2026, 10, 25), "posts": 6}]
        raise AssertionError(query)

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        self.calls.append((query, args))
        if "AS with_claims" in query:
            if self.empty:
                return dict.fromkeys(FUNNEL, 0)
            return dict(zip(FUNNEL, (40, 30, 25, 12, 9), strict=True))
        if self.empty:
            return {"runs": 0, "avg_run_seconds": None, "median_run_seconds": None}
        assert "FILTER (WHERE status = 'completed') AS median_run_seconds" in query
        return {"runs": 50, "avg_run_seconds": 42.5, "median_run_seconds": 20.25}

    async def fetchval(self, query: str, *args: object) -> int:
        self.calls.append((query, args))
        assert "FROM claims" in query
        return 0 if self.empty else 321

    async def close(self) -> None:
        return None


def test_report_days_end_on_kyiv_today() -> None:
    """The window uses Kyiv calendar days even when UTC is still on the previous day."""
    assert report_days(NOW, 3) == [date(2026, 10, 23), date(2026, 10, 24), date(2026, 10, 25)]
    assert report_days(NOW, 1) == [date(2026, 10, 25)]


def test_report_hours_cover_48_utc_hours() -> None:
    hours = report_hours(NOW)
    assert len(hours) == 48
    assert hours[-1] == datetime(2026, 10, 24, 21, tzinfo=UTC)
    assert hours[0] == datetime(2026, 10, 22, 22, tzinfo=UTC)


def test_shape_days_zero_fills_and_ignores_out_of_window_rows() -> None:
    days = [date(2026, 10, 1), date(2026, 10, 2)]
    rows = shape_days(
        days,
        [{"date": date(2026, 10, 2), "collected_posts": 3, "published_posts": None}],
        [
            {
                "date": date(2026, 9, 30),
                "completed": 5,
                "partial": 0,
                "fallback": 0,
                "failed": 0,
                "filtered_out": 0,
            }
        ],
    )
    assert rows == [
        {
            "date": "2026-10-01",
            "collected_posts": 0,
            "published_posts": 0,
            "completed": 0,
            "partial": 0,
            "fallback": 0,
            "failed": 0,
            "filtered_out": 0,
        },
        {
            "date": "2026-10-02",
            "collected_posts": 3,
            "published_posts": 0,
            "completed": 0,
            "partial": 0,
            "fallback": 0,
            "failed": 0,
            "filtered_out": 0,
        },
    ]


def test_shape_hours_accepts_aware_and_naive_hours() -> None:
    hours = [datetime(2026, 10, 24, 20, tzinfo=UTC), datetime(2026, 10, 24, 21, tzinfo=UTC)]
    rows = shape_hours(
        hours, [{"hour": datetime(2026, 10, 24, 21, tzinfo=UTC), "completed": 2, "failed": 1}]
    )
    assert rows == [
        {"hour": "2026-10-24T20:00:00Z", "completed": 0, "failed": 0},
        {"hour": "2026-10-24T21:00:00Z", "completed": 2, "failed": 1},
    ]


def test_shape_passes_lists_core_passes_in_pipeline_order() -> None:
    rows = shape_passes(
        [
            {
                "pass_name": "zeta",
                "attempts": 1,
                "repairs": 0,
                "invalid": 0,
                "failed": 1,
                "median_ms": None,
                "p95_ms": None,
                "median_completion_tokens": None,
            },
            {
                "pass_name": "candidates",
                "attempts": 2,
                "repairs": 0,
                "invalid": 0,
                "failed": 0,
                "median_ms": 10,
                "p95_ms": 20,
                "median_completion_tokens": 5,
            },
        ]
    )
    assert [row["pass_name"] for row in rows] == [
        "candidates",
        "entities",
        "claims",
        "classification",
        "zeta",
    ]
    assert rows[0]["median_ms"] == 10.0
    assert rows[1] == {
        "pass_name": "entities",
        "attempts": 0,
        "repairs": 0,
        "invalid": 0,
        "failed": 0,
        "median_ms": None,
        "p95_ms": None,
        "median_completion_tokens": None,
    }


def test_shape_models_and_totals_handle_nulls() -> None:
    models = shape_models(
        [{"model_name": "m", "pipeline_version": "v", "runs": 1, "last_used_at": None}]
    )
    assert models == [{"model_name": "m", "pipeline_version": "v", "runs": 1, "last_used_at": None}]
    assert shape_totals(None, None) == {
        "runs": 0,
        "avg_run_seconds": None,
        "median_run_seconds": None,
        "claims": 0,
    }
    assert shape_totals({"runs": 3, "avg_run_seconds": 9, "median_run_seconds": None}, 4) == {
        "runs": 3,
        "avg_run_seconds": 9.0,
        "median_run_seconds": None,
        "claims": 4,
    }


def test_shape_funnel_sums_collected_posts_and_zero_fills() -> None:
    days = [{"collected_posts": 3}, {"collected_posts": 4}]

    assert shape_funnel(None, days) == {"collected": 7, **dict.fromkeys(FUNNEL, 0)}
    assert shape_funnel({**dict.fromkeys(FUNNEL, 1), "negative": None}, [])["negative"] == 0


async def test_repository_queries_from_kyiv_midnight() -> None:
    pool = SystemPool()
    result = await SystemRepository(pool).activity(2, now=NOW)  # type: ignore[arg-type]
    starts = {args[0] for query, args in pool.calls if args and "date_trunc" not in query}
    assert starts == {datetime(2026, 10, 24, 0, 0, tzinfo=system.ZoneInfo("Europe/Kyiv"))}
    hourly = next(args for query, args in pool.calls if "date_trunc" in query)
    assert hourly == (datetime(2026, 10, 22, 22, tzinfo=UTC),)
    assert [day["date"] for day in result["days"]] == ["2026-10-24", "2026-10-25"]  # type: ignore[index]


async def test_system_activity_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_pool(_: str, **__: object) -> SystemPool:
        return SystemPool()

    monkeypatch.setattr(main.asyncpg, "create_pool", fake_pool)
    monkeypatch.setattr(system, "utc_now", lambda: NOW)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/system/activity", params={"days": 2})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"days", "funnel", "hours", "passes", "models", "channels", "totals"}
    assert body["funnel"] == {
        "collected": 12,
        "analysed": 40,
        "matched": 30,
        "with_claims": 25,
        "evaluative": 12,
        "negative": 9,
    }
    assert body["days"] == [
        {
            "date": "2026-10-24",
            "collected_posts": 0,
            "published_posts": 0,
            "completed": 40,
            "partial": 1,
            "fallback": 2,
            "failed": 3,
            "filtered_out": 4,
        },
        {
            "date": "2026-10-25",
            "collected_posts": 12,
            "published_posts": 10,
            "completed": 0,
            "partial": 0,
            "fallback": 0,
            "failed": 0,
            "filtered_out": 0,
        },
    ]
    assert len(body["hours"]) == 48
    assert body["hours"][-2] == {"hour": "2026-10-24T20:00:00Z", "completed": 7, "failed": 0}
    assert [row["pass_name"] for row in body["passes"]] == [
        "entities",
        "claims",
        "targets",
        "classification",
    ]
    assert body["passes"][3]["median_completion_tokens"] is None
    assert body["passes"][3]["p95_ms"] == 3100.5
    assert body["models"] == [
        {
            "model_name": "MamayLM",
            "pipeline_version": "inference_v3_6",
            "runs": 9,
            "last_used_at": "2026-10-24T21:00:00+00:00",
        }
    ]
    assert body["channels"] == [
        {
            "id": 1,
            "title": "INSIDER UA",
            "days": [{"date": "2026-10-24", "posts": 0}, {"date": "2026-10-25", "posts": 6}],
        },
        {
            "id": 2,
            "title": None,
            "days": [{"date": "2026-10-24", "posts": 0}, {"date": "2026-10-25", "posts": 0}],
        },
    ]
    assert body["totals"] == {
        "runs": 50,
        "avg_run_seconds": 42.5,
        "median_run_seconds": 20.25,
        "claims": 321,
    }


async def test_system_activity_defaults_to_30_days_with_empty_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_pool(_: str, **__: object) -> SystemPool:
        return SystemPool(empty=True)

    monkeypatch.setattr(main.asyncpg, "create_pool", fake_pool)
    monkeypatch.setattr(system, "utc_now", lambda: NOW)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/system/activity")
    body = response.json()
    assert response.status_code == 200
    assert len(body["days"]) == 30
    assert body["days"][0]["date"] == "2026-09-26"
    assert body["days"][-1]["date"] == "2026-10-25"
    assert all(row["completed"] == 0 for row in body["hours"])
    assert [row["pass_name"] for row in body["passes"]] == ["entities", "claims", "classification"]
    assert body["models"] == []
    assert body["funnel"] == {"collected": 0, **dict.fromkeys(FUNNEL, 0)}
    assert all(len(channel["days"]) == 30 for channel in body["channels"])
    assert body["totals"] == {
        "runs": 0,
        "avg_run_seconds": None,
        "median_run_seconds": None,
        "claims": 0,
    }


@pytest.mark.parametrize("days", ["0", "91", "-1", "abc"])
async def test_system_activity_rejects_out_of_range_days(
    monkeypatch: pytest.MonkeyPatch, days: str
) -> None:
    async def fake_pool(_: str, **__: object) -> SystemPool:
        return SystemPool()

    monkeypatch.setattr(main.asyncpg, "create_pool", fake_pool)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/system/activity", params={"days": days})
    assert response.status_code == 422
