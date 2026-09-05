"""Idle shell for the future AI analysis worker."""

import asyncio

from monitoring_common.config import BaseServiceSettings
from monitoring_common.logging import setup_logging


class AiWorkerSettings(BaseServiceSettings):
    """Settings owned by the AI analysis boundary."""

    service_name: str = "telegram-monitor-ai-worker"


async def run(stop_event: asyncio.Event | None = None) -> None:
    """Start the worker shell without calling an AI provider."""
    settings = AiWorkerSettings()
    logger = setup_logging(settings.service_name)
    logger.info("worker shell started")
    await (stop_event or asyncio.Event()).wait()


def main() -> None:
    """Run the worker process."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
