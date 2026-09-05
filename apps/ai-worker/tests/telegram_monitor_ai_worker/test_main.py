"""AI worker shell tests."""

import asyncio

from telegram_monitor_ai_worker.main import run


async def test_run_exits_when_stop_event_is_set() -> None:
    stop_event = asyncio.Event()
    stop_event.set()

    await run(stop_event)
