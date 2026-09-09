"""Launch the experimental editor using existing local database settings."""

import os
import subprocess
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values


def main() -> None:
    """Start standalone Compose without exposing database credentials in command arguments."""
    directory = Path(__file__).resolve().parents[1]
    root = directory.parents[1]
    settings = {
        **dotenv_values(root / "infra/postgres/.env"),
        **dotenv_values(root / ".env"),
        **dotenv_values(directory / ".env"),
    }
    environment = dict(os.environ)
    dsn = environment.get("ANNOTATION_POSTGRES_DSN") or settings.get("ANNOTATION_POSTGRES_DSN")
    if not dsn:
        user = quote(settings.get("POSTGRES_USER") or "telegram_monitor", safe="")
        password = quote(settings.get("POSTGRES_PASSWORD") or "change-me", safe="")
        database = quote(settings.get("POSTGRES_DB") or "telegram_monitor", safe="")
        # The editor joins the main Compose network, where PostgreSQL is named "postgres".
        # POSTGRES_PORT is its host-published port and is intentionally not used here.
        dsn = f"postgresql://{user}:{password}@postgres:5432/{database}"
    environment.update(
        ANNOTATION_POSTGRES_DSN=dsn,
        ANNOTATION_UID=str(os.getuid()),
        ANNOTATION_GID=str(os.getgid()),
    )
    subprocess.run(
        ["docker", "compose", "-f", str(directory / "compose.yaml"), "up", "--build", "-d"],
        env=environment,
        check=True,
    )


if __name__ == "__main__":
    main()
