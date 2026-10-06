"""ASGI application configured from the environment for Uvicorn and Vercel."""

from telegram_monitor_gateway.api import create_app

app = create_app()
