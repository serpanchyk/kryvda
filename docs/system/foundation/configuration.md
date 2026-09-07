# Configuration

Python services use Pydantic settings with this precedence: constructor values, environment,
local `.env`, `config.yaml`, file secrets, and defaults. Root `.env` configures Compose ports
and shared development values. Each service and PostgreSQL has a tracked `.env.example`;
real `.env` files are ignored.

All service logs are JSON and contain timestamp, logger, level, and message fields.

The Telegram scraper requires `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`,
`TELEGRAM_PHONE_NUMBER`, and `TELEGRAM_SESSION_STRING`. Local values belong in the ignored
root `.env`; deployments inject the same values from GitHub Secrets. The session string is
an authorized MTProto login secret and must be rotated if revoked.

## Creating the Telegram session

Set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE_NUMBER` in the ignored root
`.env`, then run this once from the repository root:

```bash
uv run telegram-monitor-authorize
```

The command requests the Telegram verification code and, if enabled, the two-step verification
password. It writes a single `TELEGRAM_SESSION_STRING=...` line only to the terminal; copy that
value to the ignored root `.env` for Docker Compose and to the production secret store. Never
commit it or send it in chat. Use the dedicated project account for production.
