"""One-time, interactive authorization for the scraper's Telegram account."""

import asyncio
import getpass
import sys
from typing import cast

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession


class AuthorizationSettings(BaseSettings):
    """Credentials required only while creating a reusable Telegram session."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_api_id: int
    telegram_api_hash: SecretStr
    telegram_phone_number: SecretStr


async def create_session(settings: AuthorizationSettings) -> str:
    """Authorize interactively and return a serialized session without persisting it locally."""
    client = TelegramClient(
        StringSession(),
        settings.telegram_api_id,
        settings.telegram_api_hash.get_secret_value(),
    )
    phone_number = settings.telegram_phone_number.get_secret_value()
    await client.connect()
    try:
        if not await client.is_user_authorized():
            await client.send_code_request(phone_number)
            verification_code = getpass.getpass("Telegram verification code: ")
            try:
                await client.sign_in(phone_number, verification_code)
            except SessionPasswordNeededError:
                password = getpass.getpass("Telegram two-step verification password: ")
                await client.sign_in(password=password)
        return cast(str, StringSession.save(client.session))
    finally:
        await client.disconnect()


def main() -> None:
    """Create a session string and write it only to the invoking terminal."""
    settings = AuthorizationSettings()  # type: ignore[call-arg]
    session_string = asyncio.run(create_session(settings))
    sys.stdout.write(f"TELEGRAM_SESSION_STRING={session_string}\n")


if __name__ == "__main__":
    main()
