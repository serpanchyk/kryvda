"""The Vercel entrypoint must expose an ASGI ``app`` built from environment settings."""

import runpy
from pathlib import Path

import pytest
from fastapi import FastAPI

ENTRYPOINT = Path(__file__).resolve().parents[2] / "app.py"


def test_vercel_entrypoint_exposes_configured_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
    monkeypatch.setenv("TELEGRAM_GATEWAY_TOKEN", "t" * 32)

    namespace = runpy.run_path(str(ENTRYPOINT))

    assert isinstance(namespace["app"], FastAPI)
