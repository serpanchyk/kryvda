"""Idle shell for the future Telegram collection worker."""

import asyncio

from monitoring_common.config import BaseServiceSettings
from monitoring_common.logging import setup_logging


class ScraperSettings(BaseServiceSettings):
    """Settings owned by the Telegram collection boundary."""

    service_name: str = "telegram-monitor-scraper"


async def run(stop_event: asyncio.Event | None = None) -> None:
    """Start the worker shell without collecting Telegram data."""
    settings = ScraperSettings()
    logger = setup_logging(settings.service_name)
    logger.info("worker shell started")
    await (stop_event or asyncio.Event()).wait()


def main() -> None:
    """Run the worker process."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
