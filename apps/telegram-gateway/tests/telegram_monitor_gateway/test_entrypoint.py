"""The Vercel entrypoint must expose an ASGI ``app`` built from environment settings."""

import runpy
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ENTRYPOINT = Path(__file__).resolve().parents[2] / "app.py"


def test_vercel_entrypoint_exposes_configured_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session")
    monkeypatch.setenv("TELEGRAM_GATEWAY_TOKEN", "t" * 32)

    namespace = runpy.run_path(str(ENTRYPOINT))

    assert isinstance(namespace["app"], FastAPI)


def test_missing_settings_are_reported_instead_of_crashing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in (
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_SESSION_STRING",
        "TELEGRAM_GATEWAY_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_GATEWAY_TOKEN", "short")
    monkeypatch.chdir(tmp_path)  # keep the developer's root .env out of the settings
    from telegram_monitor_gateway.asgi import build_app

    client = TestClient(build_app())
    health = client.get("/health")
    fetch = client.post("/v1/channels/fetch", json={})

    assert health.status_code == 503
    assert fetch.status_code == 503
    assert health.json() == {
        "status": "misconfigured",
        "detail": "Missing or invalid environment variables: "
        "TELEGRAM_API_HASH, TELEGRAM_GATEWAY_TOKEN, TELEGRAM_SESSION_STRING",
    }
