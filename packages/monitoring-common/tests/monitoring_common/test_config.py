"""Tests for shared configuration defaults."""

from monitoring_common.config import BaseServiceSettings


def test_settings_accept_constructor_values() -> None:
    settings = BaseServiceSettings(service_name="test-service")

    assert settings.service_name == "test-service"
    assert settings.postgres_dsn.startswith("postgresql://")
