"""API health and current-channel-avatar tests."""

from pathlib import Path

from fastapi.testclient import TestClient
from telegram_monitor_api import main
from telegram_monitor_api.main import ApiSettings, app, create_app


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "telegram-monitor-api"}


class FakePool:
    async def fetchval(self, query: str, channel_id: int) -> str | None:
        return "image/jpeg" if channel_id == 1 else None

    async def close(self) -> None:
        return None


async def fake_create_pool(_: str) -> FakePool:
    return FakePool()


def test_channel_image_serves_stored_avatar(tmp_path: Path, monkeypatch: object) -> None:
    (tmp_path / "1.avatar").write_bytes(b"\xff\xd8\xffavatar")
    monkeypatch.setattr(main.asyncpg, "create_pool", fake_create_pool)  # type: ignore[union-attr]
    client = TestClient(create_app(ApiSettings(channel_image_storage_path=tmp_path)))

    response = client.get("/channel-images/1")

    assert response.status_code == 200
    assert response.content == b"\xff\xd8\xffavatar"
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-cache"


def test_channel_image_returns_not_found_without_metadata(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setattr(main.asyncpg, "create_pool", fake_create_pool)  # type: ignore[union-attr]
    client = TestClient(create_app(ApiSettings(channel_image_storage_path=tmp_path)))

    response = client.get("/channel-images/2")

    assert response.status_code == 404
