# Telegram Monitor

Telegram target-monitoring service for a fixed ЦПК-agreed channel pool. It retains raw posts,
filters them against a human registry, and runs three focused Mamay passes for actors, atomic
claims, stance and attack rhetoric.

## Start

1. Copy `.env.example` to `.env` and `infra/postgres/.env.example` to
   `infra/postgres/.env`.
2. Create Telegram API credentials at [my.telegram.org](https://my.telegram.org), add
   `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and the dedicated account's
   `TELEGRAM_PHONE_NUMBER` to the ignored root `.env`.
3. Run `uv run telegram-monitor-authorize`, complete Telegram's login prompt, and copy the
   printed `TELEGRAM_SESSION_STRING` into `.env`.
4. Run `docker compose up --build`.
5. Open `http://localhost:8000/health`,
   `http://localhost:8000/channels/collection-health`, and `http://localhost:5173`.

The first PostgreSQL initialization seeds the approved five public Telegram channels. The
scraper retains raw post revisions and creates PostgreSQL analysis jobs. Docker Compose also
starts an internal-only LiteLLM proxy for `MamayLM-Gemma-3-27B-IT`; configure its credentials in
the root `.env` before starting Compose. The product UI remains a shell; registry and candidate
review are available through unauthenticated APIs that require deployment network controls.

See [docs/run-project.md](docs/run-project.md) for commands and
[docs/system/README.md](docs/system/README.md) for architecture.
