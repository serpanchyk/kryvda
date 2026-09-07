"""HTTP API for health and read-only collection operations."""

import asyncpg
import uvicorn
from fastapi import FastAPI
from monitoring_common.config import BaseServiceSettings
from monitoring_common.logging import setup_logging


class ApiSettings(BaseServiceSettings):
    """Settings owned by the API runtime boundary."""

    service_name: str = "telegram-monitor-api"


def create_app() -> FastAPI:
    """Build the API and its collection-health endpoint."""
    settings = ApiSettings()
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
                   last_collected_at, last_error, last_error_at
                   FROM monitored_channels ORDER BY id"""
            )
            return [dict(row) for row in rows]
        finally:
            await pool.close()

    return app


app = create_app()


def main() -> None:
    """Run the API service."""
    uvicorn.run("telegram_monitor_api.main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
