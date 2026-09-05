"""FastAPI service shell."""

import uvicorn
from fastapi import FastAPI
from monitoring_common.config import BaseServiceSettings
from monitoring_common.logging import setup_logging


class ApiSettings(BaseServiceSettings):
    """Settings owned by the API runtime boundary."""

    service_name: str = "telegram-monitor-api"


def create_app() -> FastAPI:
    """Build the API shell and its foundational health endpoint."""
    settings = ApiSettings()
    logger = setup_logging(settings.service_name)
    app = FastAPI(title="Telegram Monitor API", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        logger.info("health check")
        return {"status": "ok", "service": settings.service_name}

    return app


app = create_app()


def main() -> None:
    """Run the API service."""
    uvicorn.run("telegram_monitor_api.main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
