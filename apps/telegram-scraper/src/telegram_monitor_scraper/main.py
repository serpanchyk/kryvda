"""Telegram collection worker entry point."""

import asyncio
from pathlib import Path

import asyncpg
from monitoring_common.config import BaseServiceSettings
from monitoring_common.logging import setup_logging
from pydantic import SecretStr

from telegram_monitor_scraper.avatar_storage import ChannelAvatarStorage
from telegram_monitor_scraper.client import TelethonChannelClient
from telegram_monitor_scraper.collector import Collector
from telegram_monitor_scraper.repository import CollectionRepository


class ScraperSettings(BaseServiceSettings):
    """Settings owned by the Telegram collection boundary."""

    service_name: str = "telegram-monitor-scraper"
    telegram_api_id: int
    telegram_api_hash: SecretStr
    telegram_phone_number: SecretStr
    telegram_session_string: SecretStr
    collection_poll_interval_seconds: int = 300
    channel_image_storage_path: Path = Path("/var/lib/telegram-monitor/channel-images")


async def run(stop_event: asyncio.Event | None = None) -> None:
    """Continuously persist live posts and bounded historical evidence."""
    if stop_event is not None and stop_event.is_set():
        return
    settings = ScraperSettings()  # type: ignore[call-arg]
    logger = setup_logging(settings.service_name)
    pool = await asyncpg.create_pool(settings.postgres_dsn)
    client = TelethonChannelClient(
        settings.telegram_api_id,
        settings.telegram_api_hash.get_secret_value(),
        settings.telegram_session_string.get_secret_value(),
    )
    await client.connect(settings.telegram_phone_number.get_secret_value())
    collector = Collector(
        CollectionRepository(pool),
        client,
        ChannelAvatarStorage(settings.channel_image_storage_path),
    )
    stop = stop_event or asyncio.Event()
    logger.info("telegram collection worker started")
    try:
        while not stop.is_set():
            await collector.collect_once()
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=settings.collection_poll_interval_seconds
                )
            except TimeoutError:
                pass
    finally:
        await client.disconnect()
        await pool.close()


def main() -> None:
    """Run the collection worker."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
