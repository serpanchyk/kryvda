"""Expose health, collection status, and current channel-avatar HTTP resources."""

from pathlib import Path

import asyncpg
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from monitoring_common.config import BaseServiceSettings
from monitoring_common.logging import setup_logging


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

    return app


app = create_app()


def main() -> None:
    """Run the API service."""
    uvicorn.run("telegram_monitor_api.main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
