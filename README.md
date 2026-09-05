# Telegram Monitor

Runnable foundation for a service that will monitor a fixed ЦПК-agreed pool of Telegram
channels, retain raw posts, and later analyse entities, stance, and claims.

## Start

1. Copy `.env.example` to `.env` and `infra/postgres/.env.example` to
   `infra/postgres/.env`.
2. Run `docker compose up --build`.
3. Open `http://localhost:8000/health` and `http://localhost:5173`.

This initial revision provides runtime boundaries only. It intentionally contains no
Telegram integration, AI provider integration, database schema, migrations, or product UI.

See [docs/run-project.md](docs/run-project.md) for commands and
[docs/system/README.md](docs/system/README.md) for architecture.
