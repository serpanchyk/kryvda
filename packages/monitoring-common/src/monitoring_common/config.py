"""Configuration loading shared by Python service shells."""

from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class BaseServiceSettings(BaseSettings):
    """Base settings with environment, dotenv, and YAML support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        yaml_file="config.yaml",
        env_ignore_empty=True,
        extra="ignore",
    )

    service_name: str
    postgres_dsn: str = "postgresql://telegram_monitor:change-me@postgres:5432/telegram_monitor"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Apply documented setting precedence."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=Path("config.yaml")),
            file_secret_settings,
        )
