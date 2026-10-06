"""Settings owned by the Telegram gateway boundary."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    """Telegram credentials and the shared secret that callers must present."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    service_name: str = "telegram-monitor-gateway"
    telegram_api_id: int
    telegram_api_hash: SecretStr
    telegram_session_string: SecretStr
    telegram_gateway_token: SecretStr = Field(min_length=32)
    # Telethon sleeps through shorter flood waits; longer ones are returned to the caller as 429
    # so a request never approaches the 300-second Vercel function limit.
    telegram_flood_sleep_threshold_seconds: int = Field(default=20, ge=0, le=60)
