"""HTTP boundary that lets a firewalled scraper read Telegram through this gateway."""

import asyncio
import hmac
import time
from typing import Annotated, Protocol

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from telegram_monitor_gateway.contract import ChannelFetchRequest, ChannelFetchResponse
from telegram_monitor_gateway.json_logging import setup_logging
from telegram_monitor_gateway.settings import GatewaySettings
from telegram_monitor_gateway.telegram import (
    SessionNotAuthorizedError,
    TelegramChannelReader,
    TelegramRateLimitedError,
)


class ChannelReader(Protocol):
    """Telegram operation served by the gateway."""

    async def fetch(self, request: ChannelFetchRequest) -> ChannelFetchResponse: ...


def create_app(
    settings: GatewaySettings | None = None, reader: ChannelReader | None = None
) -> FastAPI:
    """Build the authenticated gateway application.

    Args:
        settings: Runtime settings; loaded from the environment when omitted.
        reader: Telegram reader; built from ``settings`` when omitted.

    Returns:
        Configured FastAPI application.
    """
    settings = settings or GatewaySettings()  # type: ignore[call-arg]
    channel_reader = reader or TelegramChannelReader.from_settings(settings)
    logger = setup_logging(settings.service_name)
    expected_token = settings.telegram_gateway_token.get_secret_value().encode()
    bearer = HTTPBearer(auto_error=False)
    # Telegram revokes a session used over two connections at once, so one instance never
    # serves concurrent fetches. The scraper also calls the gateway strictly sequentially.
    session_lock = asyncio.Lock()
    app = FastAPI(title="Кривда Telegram gateway", docs_url=None, redoc_url=None, openapi_url=None)

    def authorize(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> None:
        if credentials is None or not hmac.compare_digest(
            credentials.credentials.encode(), expected_token
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid gateway token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Report liveness without opening a Telegram connection."""
        return {"status": "ok", "service": settings.service_name}

    @app.post("/v1/channels/fetch", dependencies=[Depends(authorize)])
    async def fetch_channel(request: ChannelFetchRequest) -> ChannelFetchResponse:
        """Fetch one bounded snapshot of a monitored channel."""
        reference = request.channel.configured_reference
        started = time.monotonic()
        async with session_lock:
            try:
                response = await channel_reader.fetch(request)
            except TelegramRateLimitedError as error:
                logger.warning(
                    "telegram flood wait", extra={"channel": reference, "seconds": error.seconds}
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=str(error),
                    headers={"Retry-After": str(error.seconds)},
                ) from error
            except SessionNotAuthorizedError as error:
                logger.error("telegram session not authorized")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
                ) from error
            except Exception as error:
                logger.exception("telegram fetch failed", extra={"channel": reference})
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"{type(error).__name__}: {error}",
                ) from error
        logger.info(
            "telegram channel fetched",
            extra={
                "channel": reference,
                "newer_posts": len(response.newer_posts),
                "older_posts": len(response.older_posts),
                "duration_seconds": round(time.monotonic() - started, 3),
            },
        )
        return response

    return app


def create_misconfigured_app(invalid_variables: list[str]) -> FastAPI:
    """Build an application that explains a configuration error instead of crashing.

    A crash during import surfaces on Vercel only as an opaque ``FUNCTION_INVOCATION_FAILED``;
    this keeps ``/health`` able to name the missing variables without revealing any values.

    Args:
        invalid_variables: Names of missing or invalid environment variables.

    Returns:
        Application that answers every request with HTTP 503.
    """
    logger = setup_logging("telegram-monitor-gateway")
    detail = "Missing or invalid environment variables: " + ", ".join(invalid_variables)
    logger.error("gateway misconfigured", extra={"invalid_variables": invalid_variables})
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.api_route("/{path:path}", methods=["GET", "POST"])
    async def misconfigured(path: str) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "misconfigured", "detail": detail},
        )

    return app
