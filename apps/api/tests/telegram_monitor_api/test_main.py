"""API shell smoke tests."""

from fastapi.testclient import TestClient
from telegram_monitor_api.main import app


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "telegram-monitor-api"}
