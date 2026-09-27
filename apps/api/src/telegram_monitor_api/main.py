"""Expose health, collection status, and current channel-avatar HTTP resources."""

from datetime import datetime
from pathlib import Path
from typing import Literal

import asyncpg
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from monitoring_common.config import BaseServiceSettings
from monitoring_common.logging import setup_logging
from pydantic import BaseModel, Field

from telegram_monitor_api.analytics import AnalyticsRepository, EntityAnalyticsFilters
from telegram_monitor_api.registry import RegistryRepository

CoarseType = Literal["person", "organization", "state_institution", "media"]
EpistemicStatus = Literal["ствердження", "невпевнене", "питання"]
SourceKind = Literal["channel_editorial", "named_entity", "external_unnamed"]
AttributionMode = Literal["all_claims", "channel_position", "quoted_sources"]
RhetoricLabel = Literal[
    "корупція_або_особиста_вигода",
    "злочинна_або_незаконна_поведінка",
    "делегітимізація",
    "лицемірство_або_подвійні_стандарти",
    "висміювання_або_особиста_образа",
    "зовнішній_контроль_або_нелояльність",
]


class EntityCreate(BaseModel):
    """Human-approved registry entity input."""

    canonical_name: str = Field(min_length=1)
    coarse_type: CoarseType
    aliases: list[str] = Field(default_factory=list)
    monitored: bool = False


class EntityUpdate(BaseModel):
    """Mutable registry metadata."""

    canonical_name: str | None = Field(default=None, min_length=1)
    coarse_type: CoarseType | None = None
    monitored: bool | None = None


class AliasCreate(BaseModel):
    """One permanent alias approval."""

    alias: str = Field(min_length=1)


class CandidateLink(BaseModel):
    """Existing registry target for a candidate."""

    entity_id: int


class ApiSettings(BaseServiceSettings):
    """Settings owned by the API runtime boundary."""

    service_name: str = "telegram-monitor-api"
    channel_image_storage_path: Path = Path("/var/lib/telegram-monitor/channel-images")
    frontend_allowed_origin: str = "http://localhost:5173"


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Build the API health, collection-status, and channel-image endpoints.

    Args:
        settings: Runtime settings to use; load configured settings when omitted.

    Returns:
        Configured FastAPI application.
    """
    settings = settings or ApiSettings()
    logger = setup_logging(settings.service_name)
    app = FastAPI(title="Кривда API", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_allowed_origin],
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        logger.info("health check")
        return {"status": "ok", "service": settings.service_name}

    @app.get("/channels/collection-health")
    async def collection_health() -> list[dict[str, object]]:
        """Return operational state for the fixed monitored-channel pool."""
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            rows = await pool.fetch(
                """SELECT id, configured_reference, username, title, access_kind, status,
                   avatar_url, last_collected_at, last_error, last_error_at
                   FROM monitored_channels ORDER BY id"""
            )
            return [dict(row) for row in rows]
        finally:
            await pool.close()

    @app.get("/analysis/health")
    async def analysis_health() -> dict[str, object]:
        """Return the current inference queue and recent run outcome snapshot."""
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            row = await pool.fetchrow(
                """SELECT
                       count(*) FILTER (WHERE status = 'pending' AND priority = 'live')
                           AS pending_live,
                       count(*) FILTER (WHERE status = 'pending' AND priority = 'backfill')
                           AS pending_backfill,
                       count(*) FILTER (WHERE status = 'leased') AS leased,
                       count(*) FILTER (WHERE status = 'retry_scheduled')
                           AS retry_scheduled,
                       min(available_at) FILTER (WHERE status = 'retry_scheduled')
                           AS next_retry_at,
                       count(*) FILTER (WHERE status = 'failed') AS failed,
                       EXTRACT(EPOCH FROM now() - min(available_at) FILTER (
                           WHERE status = 'pending' AND available_at <= now()
                       )) AS oldest_pending_seconds
                   FROM analysis_jobs"""
            )
            runs = await pool.fetchrow(
                """SELECT
                       max(completed_at) AS last_completed_at,
                       count(*) FILTER (WHERE status IN (
                           'completed', 'completed_with_partial_classification',
                           'completed_with_entity_fallback'
                       ) AND completed_at >= now() - interval '1 hour') AS completed_last_hour,
                       count(*) FILTER (WHERE status = 'failed'
                           AND completed_at >= now() - interval '1 hour') AS failed_last_hour,
                       count(*) FILTER (WHERE status = 'completed_with_partial_classification'
                           AND completed_at >= now() - interval '1 hour') AS partial_last_hour
                   FROM analysis_runs"""
            )
            retry_rows = await pool.fetch(
                """SELECT COALESCE(last_error_kind, 'unknown') AS error_kind, count(*) AS count
                   FROM analysis_jobs WHERE status = 'retry_scheduled'
                   GROUP BY last_error_kind ORDER BY count DESC, error_kind"""
            )
            assert row is not None
            assert runs is not None
            jobs = dict(row)
            jobs["retry_by_error_kind"] = {
                str(retry_row["error_kind"]): int(retry_row["count"]) for retry_row in retry_rows
            }
            return {
                "jobs": jobs,
                "runs": dict(runs),
            }
        finally:
            await pool.close()

    @app.get("/channel-images/{channel_id}")
    async def channel_image(channel_id: int) -> FileResponse:
        """Serve a monitored channel's current locally stored Telegram avatar.

        Args:
            channel_id: Internal monitored-channel identifier.

        Returns:
            Avatar image response.

        Raises:
            HTTPException: If the channel has no stored avatar.
        """
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            content_type = await pool.fetchval(
                "SELECT avatar_content_type FROM monitored_channels "
                "WHERE id = $1 AND avatar_url IS NOT NULL",
                channel_id,
            )
        finally:
            await pool.close()
        image_path = settings.channel_image_storage_path / f"{channel_id}.avatar"
        if content_type is None or not image_path.is_file():
            raise HTTPException(status_code=404, detail="Channel image not found")
        return FileResponse(
            image_path,
            media_type=str(content_type),
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/entities")
    async def list_entities(
        q: str | None = None,
        coarse_type: CoarseType | None = None,
        monitored: bool | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        sort: Literal[
            "name",
            "mentions",
            "positive",
            "negative",
            "negative_volume",
            "negative_balance",
            "positive_volume",
            "evaluative_volume",
        ] = "name",
        limit: int = 25,
        offset: int = 0,
    ) -> dict[str, object]:
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            return await RegistryRepository(pool).list_entities(
                q, coarse_type, monitored, start, end, sort, min(max(limit, 1), 100), max(offset, 0)
            )
        finally:
            await pool.close()

    @app.get("/dashboard")
    async def dashboard(
        start: datetime | None = None, end: datetime | None = None
    ) -> dict[str, object]:
        """Return completed-analysis aggregates for the operational dashboard."""
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            return await AnalyticsRepository(pool).dashboard(start, end)
        finally:
            await pool.close()

    @app.get("/entities/{entity_id}/analytics")
    async def entity_analytics(
        entity_id: int,
        channel_id: int | None = None,
        stance: Literal["позитивне", "негативне"] | None = None,
        rhetoric: RhetoricLabel | None = None,
        epistemic_status: EpistemicStatus | None = None,
        source_kind: SourceKind | None = None,
        source_entity_id: int | None = None,
        attribution_mode: AttributionMode | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 25,
        offset: int = 0,
        sort: Literal[
            "negative_volume", "negative_balance", "positive_volume", "evaluative_volume"
        ] = "evaluative_volume",
    ) -> dict[str, object]:
        """Return an entity profile and its auditable channel comparison."""
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            filters = EntityAnalyticsFilters(
                channel_id,
                stance,
                rhetoric,
                epistemic_status,
                source_kind,
                source_entity_id,
                attribution_mode,
            )
            result = await AnalyticsRepository(pool).entity(
                entity_id, filters, start, end, min(max(limit, 1), 100), max(offset, 0), sort
            )
            if result is None:
                raise HTTPException(status_code=404, detail="Monitored entity not found")
            return result
        finally:
            await pool.close()

    @app.get("/entities/{entity_id}/source-actors")
    async def entity_source_actors(
        entity_id: int,
        q: str | None = None,
        channel_id: int | None = None,
        stance: Literal["позитивне", "негативне"] | None = None,
        rhetoric: RhetoricLabel | None = None,
        epistemic_status: EpistemicStatus | None = None,
        attribution_mode: AttributionMode | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> dict[str, object]:
        """Return named actors with claims in one filtered entity profile."""
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            filters = EntityAnalyticsFilters(
                channel_id=channel_id,
                stance=stance,
                rhetoric=rhetoric,
                epistemic_status=epistemic_status,
                attribution_mode=attribution_mode,
            )
            return await AnalyticsRepository(pool).source_actors(
                entity_id, filters, start, end, q, min(max(limit, 1), 100), max(offset, 0)
            )
        finally:
            await pool.close()

    @app.get("/entities/{entity_id}/evidence")
    async def entity_evidence(
        entity_id: int,
        channel_id: int | None = None,
        stance: Literal["позитивне", "негативне"] | None = None,
        rhetoric: RhetoricLabel | None = None,
        epistemic_status: EpistemicStatus | None = None,
        source_kind: SourceKind | None = None,
        source_entity_id: int | None = None,
        attribution_mode: AttributionMode | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> dict[str, object]:
        """Return claims that support a filtered entity aggregate."""
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            filters = EntityAnalyticsFilters(
                channel_id,
                stance,
                rhetoric,
                epistemic_status,
                source_kind,
                source_entity_id,
                attribution_mode,
            )
            return await AnalyticsRepository(pool).evidence(
                entity_id, filters, start, end, min(max(limit, 1), 100), max(offset, 0)
            )
        finally:
            await pool.close()

    @app.get("/channels")
    async def channels(
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 25,
        offset: int = 0,
        sort: Literal[
            "negative_volume", "negative_balance", "positive_volume", "evaluative_volume"
        ] = "evaluative_volume",
    ) -> dict[str, object]:
        """Return comparable channel analysis profiles."""
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            return await AnalyticsRepository(pool).channels(
                start, end, min(max(limit, 1), 100), max(offset, 0), sort
            )
        finally:
            await pool.close()

    @app.get("/channels/{channel_id}/analytics")
    async def channel_analytics(
        channel_id: int,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 25,
        offset: int = 0,
        sort: Literal[
            "negative_volume", "negative_balance", "positive_volume", "evaluative_volume"
        ] = "negative_volume",
    ) -> dict[str, object]:
        """Return one channel analytics profile."""
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            result = await AnalyticsRepository(pool).channel(
                channel_id,
                start,
                end,
                min(max(limit, 1), 100),
                max(offset, 0),
                sort,
            )
            if result is None:
                raise HTTPException(status_code=404, detail="Channel not found")
            return result
        finally:
            await pool.close()

    @app.get("/claims")
    async def claims(
        search: str | None = None,
        entity_id: int | None = None,
        channel_id: int | None = None,
        stance: Literal["позитивне", "негативне", "відсутнє"] | None = None,
        rhetoric: RhetoricLabel | None = None,
        epistemic_status: EpistemicStatus | None = None,
        source_kind: SourceKind | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        sort: Literal["newest", "oldest"] = "newest",
        limit: int = 25,
        offset: int = 0,
    ) -> dict[str, object]:
        """Return a paginated, filterable list of completed analytical claims."""
        safe_limit = min(max(limit, 1), 100)
        safe_offset = max(offset, 0)
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            return await AnalyticsRepository(pool).claims(
                search,
                entity_id,
                channel_id,
                stance,
                rhetoric,
                epistemic_status,
                source_kind,
                start,
                end,
                sort,
                safe_limit,
                safe_offset,
            )
        finally:
            await pool.close()

    @app.get("/posts/{post_id}")
    async def post_detail(post_id: int) -> dict[str, object]:
        """Return a source post and the completed claims extracted from it."""
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            result = await AnalyticsRepository(pool).post(post_id)
            if result is None:
                raise HTTPException(status_code=404, detail="Post not found")
            return result
        finally:
            await pool.close()

    @app.post("/entities", status_code=201)
    async def create_entity(value: EntityCreate) -> dict[str, int]:
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            try:
                entity_id, jobs = await RegistryRepository(pool).create_entity(
                    value.canonical_name,
                    value.coarse_type,
                    value.aliases,
                    value.monitored,
                )
            except asyncpg.UniqueViolationError as error:
                raise HTTPException(
                    status_code=409, detail="Entity or alias already exists"
                ) from error
            return {"id": entity_id, "backfill_jobs_enqueued": jobs}
        finally:
            await pool.close()

    @app.patch("/entities/{entity_id}")
    async def update_entity(entity_id: int, value: EntityUpdate) -> dict[str, int]:
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            jobs = await RegistryRepository(pool).update_entity(
                entity_id, value.canonical_name, value.coarse_type, value.monitored
            )
            if jobs is None:
                raise HTTPException(status_code=404, detail="Entity not found")
            return {"id": entity_id, "backfill_jobs_enqueued": jobs}
        finally:
            await pool.close()

    @app.post("/entities/{entity_id}/aliases", status_code=201)
    async def add_alias(entity_id: int, value: AliasCreate) -> dict[str, int]:
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            try:
                jobs = await RegistryRepository(pool).add_alias(entity_id, value.alias)
            except asyncpg.UniqueViolationError as error:
                raise HTTPException(status_code=409, detail="Alias already exists") from error
            if jobs is None:
                raise HTTPException(status_code=404, detail="Entity not found")
            return {"id": entity_id, "backfill_jobs_enqueued": jobs}
        finally:
            await pool.close()

    @app.get("/entity-candidates")
    async def list_entity_candidates(
        status: Literal["pending", "linked", "ignored"] = "pending",
    ) -> list[dict[str, object]]:
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            return await RegistryRepository(pool).list_candidates(status)
        finally:
            await pool.close()

    @app.post("/entity-candidates/{candidate_id}/link")
    async def link_candidate(candidate_id: int, value: CandidateLink) -> dict[str, bool | int]:
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            jobs = await RegistryRepository(pool).link_candidate(candidate_id, value.entity_id)
            if jobs is None:
                raise HTTPException(status_code=404, detail="Candidate or entity not found")
            return {"linked": True, "backfill_jobs_enqueued": jobs}
        finally:
            await pool.close()

    @app.post("/entity-candidates/{candidate_id}/create-entity", status_code=201)
    async def create_candidate_entity(candidate_id: int, value: EntityCreate) -> dict[str, int]:
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        repository = RegistryRepository(pool)
        try:
            entity_id, jobs = await repository.create_entity(
                value.canonical_name,
                value.coarse_type,
                value.aliases,
                value.monitored,
            )
            if await repository.link_candidate(candidate_id, entity_id) is None:
                raise HTTPException(status_code=404, detail="Candidate not found")
            return {"id": entity_id, "backfill_jobs_enqueued": jobs}
        finally:
            await pool.close()

    @app.post("/entity-candidates/{candidate_id}/ignore")
    async def ignore_candidate(candidate_id: int) -> dict[str, bool]:
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            if not await RegistryRepository(pool).ignore_candidate(candidate_id):
                raise HTTPException(status_code=404, detail="Pending candidate not found")
            return {"ignored": True}
        finally:
            await pool.close()

    @app.get("/entities/{entity_id}/alias-candidates")
    async def list_alias_candidates(entity_id: int) -> list[dict[str, object]]:
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            return await RegistryRepository(pool).list_alias_candidates(entity_id)
        finally:
            await pool.close()

    @app.post("/alias-candidates/{candidate_id}/approve")
    async def approve_alias_candidate(candidate_id: int) -> dict[str, int]:
        return await _review_alias_candidate(settings, candidate_id, True)

    @app.post("/alias-candidates/{candidate_id}/ignore")
    async def ignore_alias_candidate(candidate_id: int) -> dict[str, int]:
        return await _review_alias_candidate(settings, candidate_id, False)

    return app


async def _review_alias_candidate(
    settings: ApiSettings, candidate_id: int, approve: bool
) -> dict[str, int]:
    pool = await asyncpg.create_pool(settings.postgres_dsn)
    try:
        jobs = await RegistryRepository(pool).review_alias_candidate(candidate_id, approve)
        if jobs is None:
            raise HTTPException(status_code=404, detail="Pending alias candidate not found")
        return {"id": candidate_id, "backfill_jobs_enqueued": jobs}
    finally:
        await pool.close()


app = create_app()


def main() -> None:
    """Run the API service."""
    uvicorn.run("telegram_monitor_api.main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
