"""Telegram collection worker entry point."""

import asyncio
from pathlib import Path

import asyncpg
from monitoring_common.config import BaseServiceSettings
from monitoring_common.logging import setup_logging
from pydantic import Field, SecretStr

from telegram_monitor_scraper.avatar_storage import ChannelAvatarStorage
from telegram_monitor_scraper.collector import Collector
from telegram_monitor_scraper.gateway_client import GatewayChannelClient
from telegram_monitor_scraper.repository import CollectionRepository


class ScraperSettings(BaseServiceSettings):
    """Settings owned by the Telegram collection boundary."""

    service_name: str = "telegram-monitor-scraper"
    telegram_gateway_url: str
    telegram_gateway_token: SecretStr
    # Longer than the gateway's 300-second Vercel limit, so the gateway reports timeouts first.
    telegram_gateway_timeout_seconds: float = 330
    collection_poll_interval_seconds: int = 3600
    collection_page_size: int = Field(default=200, ge=1, le=500)
    collection_max_pages_per_channel: int = Field(default=10, ge=1)
    channel_image_storage_path: Path = Path("/var/lib/telegram-monitor/channel-images")


async def run(stop_event: asyncio.Event | None = None) -> None:
    """Continuously persist live posts and bounded historical evidence."""
    if stop_event is not None and stop_event.is_set():
        return
    settings = ScraperSettings()  # type: ignore[call-arg]
    logger = setup_logging(settings.service_name)
    pool = await asyncpg.create_pool(settings.postgres_dsn)
    client = GatewayChannelClient.connect(
        settings.telegram_gateway_url,
        settings.telegram_gateway_token.get_secret_value(),
        settings.telegram_gateway_timeout_seconds,
        settings.collection_page_size,
    )
    collector = Collector(
        CollectionRepository(pool),
        client,
        ChannelAvatarStorage(settings.channel_image_storage_path),
        settings.collection_max_pages_per_channel,
    )
    stop = stop_event or asyncio.Event()
    logger.info(
        "telegram collection worker started",
        extra={
            "gateway_url": settings.telegram_gateway_url,
            "poll_interval_seconds": settings.collection_poll_interval_seconds,
        },
    )
    try:
        while not stop.is_set():
            await collector.collect_once()
            logger.info("telegram collection run finished")
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=settings.collection_poll_interval_seconds
                )
            except TimeoutError:
                pass
    finally:
        await client.aclose()
        await pool.close()


def main() -> None:
    """Run the collection worker."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
