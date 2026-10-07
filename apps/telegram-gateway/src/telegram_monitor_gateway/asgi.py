"""ASGI application configured from the environment for Uvicorn and Vercel."""

from fastapi import FastAPI
from pydantic import ValidationError

from telegram_monitor_gateway.api import create_app, create_misconfigured_app
from telegram_monitor_gateway.settings import GatewaySettings


def build_app() -> FastAPI:
    """Build the gateway, or a diagnostic app when environment settings are invalid."""
    try:
        settings = GatewaySettings()  # type: ignore[call-arg]
    except ValidationError as error:
        names = sorted({str(item["loc"][0]).upper() for item in error.errors() if item["loc"]})
        return create_misconfigured_app(names)
    return create_app(settings)


app = build_app()
