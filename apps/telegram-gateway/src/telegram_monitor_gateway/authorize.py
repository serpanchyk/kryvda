"""One-time, interactive authorization for the scraper's Telegram account."""

import asyncio
import getpass
import sys
from typing import Any, cast

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from telethon import TelegramClient
from telethon.errors import FloodWaitError, SendCodeUnavailableError, SessionPasswordNeededError
from telethon.sessions import StringSession

# Where Telegram delivered the login code, keyed by the Telethon ``SentCodeType*`` class name.
_DELIVERY = {
    "SentCodeTypeApp": (
        "у застосунок Telegram на іншому пристрої, де цей акаунт уже відкрито "
        "(службовий чат «Telegram»), а не SMS"
    ),
    "SentCodeTypeSms": "SMS-повідомленням",
    "SentCodeTypeFirebaseSms": "SMS-повідомленням",
    "SentCodeTypeCall": "голосовим дзвінком",
    "SentCodeTypeFlashCall": "дзвінком: код — останні цифри номера, що дзвонив",
    "SentCodeTypeMissedCall": "пропущеним дзвінком: код — останні цифри номера, що дзвонив",
    "SentCodeTypeFragmentSms": "через Fragment (fragment.com), бо номер анонімний",
    "SentCodeTypeEmailCode": "на пошту, прив'язану до входу в акаунт",
    "SentCodeTypeSetUpEmailRequired": (
        "нікуди: Telegram вимагає спершу прив'язати пошту для входу. Увійдіть в акаунт в "
        "офіційному застосунку, додайте пошту в налаштуваннях і повторіть"
    ),
}


def describe_delivery(sent_code: Any) -> str:
    """Explain in Ukrainian where Telegram sent the code and what a resend would use.

    Args:
        sent_code: Telethon ``auth.SentCode`` returned by a code request.

    Returns:
        Operator-facing description written to the terminal.
    """
    kind = type(getattr(sent_code, "type", None)).__name__
    message = f"Код надіслано {_DELIVERY.get(kind, kind)}."
    next_type = getattr(sent_code, "next_type", None)
    if next_type is not None:
        next_kind = type(next_type).__name__
        message += f" Повторний запит надішле код {_DELIVERY.get(next_kind, next_kind)}"
        timeout = getattr(sent_code, "timeout", None)
        message += f" (не раніше ніж через {timeout} с)." if timeout else "."
    return message


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
            sent_code = await client.send_code_request(phone_number)
            sys.stderr.write(describe_delivery(sent_code) + "\n")
            while True:
                verification_code = getpass.getpass(
                    "Telegram verification code (порожній Enter — запросити код ще раз): "
                ).strip()
                if verification_code:
                    break
                # Telethon resends through auth.resendCode for an already requested number.
                try:
                    sent_code = await client.send_code_request(phone_number)
                except SendCodeUnavailableError:
                    # The previously delivered code stays valid; keep waiting for it.
                    sys.stderr.write(
                        "Інших способів доставки для цього номера немає. Введіть код, уже "
                        "надісланий раніше: " + describe_delivery(sent_code) + "\n"
                    )
                    continue
                sys.stderr.write(describe_delivery(sent_code) + "\n")
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
    try:
        session_string = asyncio.run(create_session(settings))
    except FloodWaitError as error:
        sys.stderr.write(
            f"Telegram тимчасово блокує запити коду для цього номера: зачекайте {error.seconds} с "
            "і не повторюйте запит раніше, інакше очікування зросте.\n"
        )
        raise SystemExit(1) from error
    sys.stdout.write(f"TELEGRAM_SESSION_STRING={session_string}\n")


if __name__ == "__main__":
    main()
