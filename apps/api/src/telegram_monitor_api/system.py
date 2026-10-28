"""Read-only system-dynamics aggregates for the «Система» operational page."""

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

REPORT_TIMEZONE = "Europe/Kyiv"
_REPORT_ZONE = ZoneInfo(REPORT_TIMEZONE)
HOURS_WINDOW = 48

# Passes that every response lists, even with no attempts; other recorded passes are appended.
_REQUIRED_PASSES = ("entities", "claims", "classification")
_PASS_ORDER = ("candidates", "entities", "claims", "targets", "classification", "affiliations")

# A superseded run finished successfully before a newer run of its revision replaced it, so it
# still counts as completed processing work.
_SUCCESS_STATUSES = (
    "'completed', 'completed_with_partial_classification', "
    "'completed_with_entity_fallback', 'superseded'"
)
_FINISHED_FILTER = "status NOT IN ('running', 'retry_scheduled')"
_DAY = f"AT TIME ZONE '{REPORT_TIMEZONE}')::date"

POSTS_DAILY_SQL = f"""SELECT day AS date, sum(collected) AS collected_posts,
       sum(published) AS published_posts
FROM (
    SELECT (created_at {_DAY} AS day, 1 AS collected, 0 AS published
    FROM raw_posts WHERE created_at >= $1
    UNION ALL
    SELECT (published_at {_DAY}, 0, 1
    FROM raw_posts WHERE published_at >= $1
) AS post_days
GROUP BY day"""

RUNS_DAILY_SQL = f"""SELECT (completed_at {_DAY} AS date,
    count(*) FILTER (WHERE status IN ('completed', 'superseded')) AS completed,
    count(*) FILTER (WHERE status = 'completed_with_partial_classification') AS partial,
    count(*) FILTER (WHERE status = 'completed_with_entity_fallback') AS fallback,
    count(*) FILTER (WHERE status = 'failed') AS failed,
    count(*) FILTER (WHERE status = 'filtered_out') AS filtered_out
FROM analysis_runs
WHERE completed_at >= $1 AND {_FINISHED_FILTER}
GROUP BY 1"""

RUNS_HOURLY_SQL = f"""SELECT date_trunc('hour', completed_at AT TIME ZONE 'UTC') AS hour,
    count(*) FILTER (WHERE status IN ({_SUCCESS_STATUSES})) AS completed,
    count(*) FILTER (WHERE status = 'failed') AS failed
FROM analysis_runs
WHERE completed_at >= $1 AND {_FINISHED_FILTER}
GROUP BY 1"""

PASSES_SQL = """SELECT pass_name, count(*) AS attempts,
    count(*) FILTER (WHERE attempt_kind NOT IN ('primary', 'batch_primary')) AS repairs,
    count(*) FILTER (WHERE status = 'invalid') AS invalid,
    count(*) FILTER (WHERE status = 'failed') AS failed,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms) AS median_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY completion_tokens)
        AS median_completion_tokens
FROM inference_pass_attempts
WHERE created_at >= $1
GROUP BY pass_name"""

MODELS_SQL = """SELECT model_name, pipeline_version, count(*) AS runs,
    max(created_at) AS last_used_at
FROM analysis_runs
WHERE created_at >= $1
GROUP BY model_name, pipeline_version
ORDER BY runs DESC, last_used_at DESC NULLS LAST, model_name, pipeline_version"""

CHANNELS_SQL = "SELECT id, title FROM monitored_channels ORDER BY id"

CHANNEL_POSTS_DAILY_SQL = f"""SELECT channel_id, (created_at {_DAY} AS date, count(*) AS posts
FROM raw_posts
WHERE created_at >= $1
GROUP BY 1, 2"""

RUN_TOTALS_SQL = f"""SELECT count(*) AS runs,
    avg(EXTRACT(EPOCH FROM completed_at - created_at))::float8 AS avg_run_seconds,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM completed_at - created_at))
        FILTER (WHERE status = 'completed') AS median_run_seconds
FROM analysis_runs
WHERE completed_at >= $1 AND {_FINISHED_FILTER}"""

CLAIM_TOTAL_SQL = f"""SELECT count(*)
FROM claims AS claim
JOIN analysis_runs AS run ON run.id = claim.run_id
WHERE run.completed_at >= $1 AND run.{_FINISHED_FILTER}"""

_MONITORED_STANCE = """EXISTS (
        SELECT 1 FROM claims AS claim
        JOIN claim_target_classifications AS target ON target.claim_id = claim.id
        JOIN post_entities AS entity ON entity.id = target.post_entity_id
        WHERE claim.run_id = run.id AND entity.monitored AND target.stance {condition})"""

# Over the whole history: each analysed post revision once, however often it was re-analysed.
FUNNEL_SQL = f"""SELECT count(DISTINCT run.post_revision_id) AS analysed,
    count(DISTINCT run.post_revision_id) FILTER (WHERE run.status <> 'filtered_out') AS matched,
    count(DISTINCT run.post_revision_id) FILTER (
        WHERE EXISTS (SELECT 1 FROM claims AS claim WHERE claim.run_id = run.id)
    ) AS with_claims,
    count(DISTINCT run.post_revision_id) FILTER (
        WHERE {_MONITORED_STANCE.format(condition="<> 'відсутнє'")}
    ) AS evaluative,
    count(DISTINCT run.post_revision_id) FILTER (
        WHERE {_MONITORED_STANCE.format(condition="= 'негативне'")}
    ) AS negative
FROM analysis_runs AS run
WHERE run.status IN ({_SUCCESS_STATUSES}, 'filtered_out')"""

COLLECTED_TOTAL_SQL = "SELECT count(*) FROM raw_posts"

_RUN_DAY_KEYS = ("completed", "partial", "fallback", "failed", "filtered_out")
_FUNNEL_KEYS = ("analysed", "matched", "with_claims", "evaluative", "negative")
_PASS_COUNT_KEYS = ("attempts", "repairs", "invalid", "failed")
_PASS_METRIC_KEYS = ("median_ms", "p95_ms", "median_completion_tokens")


def utc_now() -> datetime:
    """Return the current aware UTC time; tests replace it to freeze the clock."""
    return datetime.now(UTC)


def report_days(now: datetime, days: int) -> list[date]:
    """Return the Kyiv calendar days of a window that ends today in Kyiv, oldest first."""
    today = now.astimezone(_REPORT_ZONE).date()
    return [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def report_hours(now: datetime) -> list[datetime]:
    """Return the last 48 UTC hour starts, oldest first, ending with the current hour."""
    current = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return [current - timedelta(hours=offset) for offset in range(HOURS_WINDOW - 1, -1, -1)]


def day_start(day: date) -> datetime:
    """Return the instant a Kyiv calendar day begins."""
    return datetime.combine(day, time.min, tzinfo=_REPORT_ZONE)


def _count(row: Mapping[str, Any] | None, key: str) -> int:
    if row is None or row[key] is None:
        return 0
    return int(row[key])


def _metric(row: Mapping[str, Any] | None, key: str) -> float | None:
    if row is None or row[key] is None:
        return None
    return float(row[key])


def _as_utc(moment: datetime) -> datetime:
    """Treat a naive database hour as UTC, matching the `AT TIME ZONE 'UTC'` truncation."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def shape_days(
    days: Sequence[date],
    post_rows: Sequence[Mapping[str, Any]],
    run_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, object]]:
    """Merge post and run counts into one zero-filled row per Kyiv day."""
    posts = {row["date"]: row for row in post_rows}
    runs = {row["date"]: row for row in run_rows}
    result: list[dict[str, object]] = []
    for day in days:
        post = posts.get(day)
        run = runs.get(day)
        result.append(
            {
                "date": day.isoformat(),
                "collected_posts": _count(post, "collected_posts"),
                "published_posts": _count(post, "published_posts"),
                **{key: _count(run, key) for key in _RUN_DAY_KEYS},
            }
        )
    return result


def shape_hours(
    hours: Sequence[datetime], rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, object]]:
    """Return one zero-filled run-outcome row per UTC hour."""
    by_hour = {_as_utc(row["hour"]): row for row in rows}
    return [
        {
            "hour": hour.isoformat().replace("+00:00", "Z"),
            "completed": _count(by_hour.get(hour), "completed"),
            "failed": _count(by_hour.get(hour), "failed"),
        }
        for hour in hours
    ]


def _pass_rank(name: str) -> tuple[int, str]:
    if name in _PASS_ORDER:
        return _PASS_ORDER.index(name), name
    return len(_PASS_ORDER), name


def shape_passes(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, object]]:
    """Return pass reliability in pipeline order, always listing the three core passes."""
    by_name: dict[str, Mapping[str, Any] | None] = {name: None for name in _REQUIRED_PASSES}
    by_name.update({str(row["pass_name"]): row for row in rows})
    return [
        {
            "pass_name": name,
            **{key: _count(by_name[name], key) for key in _PASS_COUNT_KEYS},
            **{key: _metric(by_name[name], key) for key in _PASS_METRIC_KEYS},
        }
        for name in sorted(by_name, key=_pass_rank)
    ]


def shape_models(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, object]]:
    """Return model and pipeline-version usage in database order (most runs first)."""
    result: list[dict[str, object]] = []
    for row in rows:
        last_used = row["last_used_at"]
        result.append(
            {
                "model_name": str(row["model_name"]),
                "pipeline_version": str(row["pipeline_version"]),
                "runs": int(row["runs"]),
                "last_used_at": _as_utc(last_used).isoformat() if last_used else None,
            }
        )
    return result


def shape_channels(
    days: Sequence[date],
    channel_rows: Sequence[Mapping[str, Any]],
    post_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, object]]:
    """Return every monitored channel with a zero-filled collected-post series."""
    counts = {(int(row["channel_id"]), row["date"]): int(row["posts"]) for row in post_rows}
    return [
        {
            "id": int(channel["id"]),
            "title": channel["title"],
            "days": [
                {"date": day.isoformat(), "posts": counts.get((int(channel["id"]), day), 0)}
                for day in days
            ],
        }
        for channel in channel_rows
    ]


def shape_totals(run_row: Mapping[str, Any] | None, claims: object) -> dict[str, object]:
    """Return window totals; durations are null when no matching run finished."""
    return {
        "runs": _count(run_row, "runs"),
        "avg_run_seconds": _metric(run_row, "avg_run_seconds"),
        "median_run_seconds": _metric(run_row, "median_run_seconds"),
        "claims": int(claims) if isinstance(claims, int) else 0,
    }


def shape_funnel(row: Mapping[str, Any] | None, collected: object) -> dict[str, int]:
    """Return how many posts reached each analysis stage, after the collected-post total."""
    return {
        "collected": int(collected) if isinstance(collected, int) else 0,
        **{key: _count(row, key) for key in _FUNNEL_KEYS},
    }


class SystemRepository:
    """Read pipeline throughput, reliability and collection dynamics without writes."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def activity(self, days: int, now: datetime | None = None) -> dict[str, object]:
        """Return system dynamics for a window of Kyiv days that ends today.

        Args:
            days: Number of Kyiv calendar days, including today.
            now: Reference instant; the current UTC time when omitted.

        Returns:
            Zero-filled daily, hourly and per-channel series with pass, model and total
            aggregates for the window.
        """
        moment = now or utc_now()
        calendar = report_days(moment, days)
        hours = report_hours(moment)
        start = day_start(calendar[0])
        post_rows = await self._pool.fetch(POSTS_DAILY_SQL, start)
        run_rows = await self._pool.fetch(RUNS_DAILY_SQL, start)
        hour_rows = await self._pool.fetch(RUNS_HOURLY_SQL, hours[0])
        pass_rows = await self._pool.fetch(PASSES_SQL, start)
        model_rows = await self._pool.fetch(MODELS_SQL, start)
        channel_rows = await self._pool.fetch(CHANNELS_SQL)
        channel_post_rows = await self._pool.fetch(CHANNEL_POSTS_DAILY_SQL, start)
        totals = await self._pool.fetchrow(RUN_TOTALS_SQL, start)
        claims = await self._pool.fetchval(CLAIM_TOTAL_SQL, start)
        return {
            "days": shape_days(calendar, post_rows, run_rows),
            "hours": shape_hours(hours, hour_rows),
            "passes": shape_passes(pass_rows),
            "models": shape_models(model_rows),
            "channels": shape_channels(calendar, channel_rows, channel_post_rows),
            "totals": shape_totals(totals, claims),
        }

    async def funnel(self) -> dict[str, int]:
        """Return how many posts reached each analysis stage over the whole history."""
        row = await self._pool.fetchrow(FUNNEL_SQL)
        collected = await self._pool.fetchval(COLLECTED_TOTAL_SQL)
        return shape_funnel(row, collected)
