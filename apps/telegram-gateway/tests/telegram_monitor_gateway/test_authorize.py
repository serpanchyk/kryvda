"""Tests for one-time Telegram session authorization."""

from typing import Any

import pytest
from telegram_monitor_gateway import authorize


class FakeTelegramClient:
    """Minimal asynchronous Telethon substitute for authorization tests."""

    def __init__(self, authorized: bool = False, require_password: bool = False) -> None:
        self.authorized = authorized
        self.require_password = require_password
        self.connected = False
        self.disconnected = False
        self.code_requested_for: str | None = None
        self.sign_in_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.session = object()

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def is_user_authorized(self) -> bool:
        return self.authorized

    async def send_code_request(self, phone_number: str) -> object:
        self.code_requested_for = phone_number
        self.code_requests = getattr(self, "code_requests", 0) + 1
        return SentCode(SentCodeTypeApp(), SentCodeTypeSms(), 60)

    async def sign_in(self, *args: Any, **kwargs: Any) -> None:
        self.sign_in_calls.append((args, kwargs))
        if self.require_password and len(self.sign_in_calls) == 1:
            raise NeedsPassword()


class SentCodeTypeApp:
    """Stand-in for Telethon's in-app code delivery type."""


class SentCodeTypeSms:
    """Stand-in for Telethon's SMS code delivery type."""


class SentCode:
    def __init__(self, kind: object, next_type: object | None, timeout: int | None) -> None:
        self.type = kind
        self.next_type = next_type
        self.timeout = timeout


class NeedsPassword(Exception):
    """Stand-in for Telegram's two-step verification exception."""


def settings() -> authorize.AuthorizationSettings:
    """Build explicit settings without reading developer environment files."""
    return authorize.AuthorizationSettings(
        telegram_api_id=1,
        telegram_api_hash="hash",
        telegram_phone_number="+380000000000",
    )


@pytest.mark.asyncio
async def test_create_session_requests_code_and_closes_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeTelegramClient()
    monkeypatch.setattr(authorize, "TelegramClient", lambda *_: client)
    monkeypatch.setattr(authorize.StringSession, "save", lambda _: "serialized")
    monkeypatch.setattr(authorize.getpass, "getpass", lambda _: "12345")

    session_string = await authorize.create_session(settings())

    assert session_string == "serialized"
    assert client.code_requested_for == "+380000000000"
    assert client.sign_in_calls == [(("+380000000000", "12345"), {})]
    assert client.disconnected


@pytest.mark.asyncio
async def test_create_session_handles_two_step_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeTelegramClient(require_password=True)
    prompts = iter(["12345", "password"])
    monkeypatch.setattr(authorize, "TelegramClient", lambda *_: client)
    monkeypatch.setattr(authorize, "SessionPasswordNeededError", NeedsPassword)
    monkeypatch.setattr(authorize.StringSession, "save", lambda _: "serialized")
    monkeypatch.setattr(authorize.getpass, "getpass", lambda _: next(prompts))

    await authorize.create_session(settings())

    assert client.sign_in_calls == [
        (("+380000000000", "12345"), {}),
        ((), {"password": "password"}),
    ]


def test_main_writes_only_session_assignment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def create_serialized_session(_: authorize.AuthorizationSettings) -> str:
        return "serialized"

    configured_settings = settings()
    monkeypatch.setattr(authorize, "AuthorizationSettings", lambda: configured_settings)
    monkeypatch.setattr(authorize, "create_session", create_serialized_session)

    authorize.main()

    assert capsys.readouterr().out == "TELEGRAM_SESSION_STRING=serialized\n"


def test_delivery_description_names_the_channel_and_resend() -> None:
    message = authorize.describe_delivery(SentCode(SentCodeTypeApp(), SentCodeTypeSms(), 60))

    assert "застосунок Telegram" in message
    assert "SMS-повідомленням (не раніше ніж через 60 с)" in message
    assert authorize.describe_delivery(SentCode(SentCodeTypeSms(), None, None)) == (
        "Код надіслано SMS-повідомленням."
    )


@pytest.mark.asyncio
async def test_empty_code_requests_another_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeTelegramClient()
    answers = iter(["", "12345"])
    monkeypatch.setattr(authorize, "TelegramClient", lambda *_: client)
    monkeypatch.setattr(authorize.StringSession, "save", lambda _: "serialized")
    monkeypatch.setattr(authorize.getpass, "getpass", lambda _: next(answers))

    assert await authorize.create_session(settings()) == "serialized"
    assert client.code_requests == 2
    assert client.sign_in_calls[0][0] == ("+380000000000", "12345")


@pytest.mark.asyncio
async def test_unavailable_resend_keeps_waiting_for_the_first_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoResendClient(FakeTelegramClient):
        async def send_code_request(self, phone_number: str) -> object:
            if getattr(self, "code_requests", 0):
                raise authorize.SendCodeUnavailableError(request=None)
            return await super().send_code_request(phone_number)

    client = NoResendClient()
    answers = iter(["", "54321"])
    monkeypatch.setattr(authorize, "TelegramClient", lambda *_: client)
    monkeypatch.setattr(authorize.StringSession, "save", lambda _: "serialized")
    monkeypatch.setattr(authorize.getpass, "getpass", lambda _: next(answers))

    assert await authorize.create_session(settings()) == "serialized"
    assert client.sign_in_calls[0][0] == ("+380000000000", "54321")
