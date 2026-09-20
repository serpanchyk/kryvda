"""Expose health, collection status, and current channel-avatar HTTP resources."""

from pathlib import Path
from typing import Literal

import asyncpg
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from monitoring_common.config import BaseServiceSettings
from monitoring_common.logging import setup_logging
from pydantic import BaseModel, Field

from telegram_monitor_api.registry import RegistryRepository

CoarseType = Literal["person", "organization", "state_institution", "media"]


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


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Build the API health, collection-status, and channel-image endpoints.

    Args:
        settings: Runtime settings to use; load configured settings when omitted.

    Returns:
        Configured FastAPI application.
    """
    settings = settings or ApiSettings()
    logger = setup_logging(settings.service_name)
    app = FastAPI(title="Telegram Monitor API", version="0.1.0")

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
            assert row is not None
            assert runs is not None
            return {
                "jobs": dict(row),
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
    async def list_entities(monitored: bool | None = None) -> list[dict[str, object]]:
        pool = await asyncpg.create_pool(settings.postgres_dsn)
        try:
            return await RegistryRepository(pool).list_entities(monitored)
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
