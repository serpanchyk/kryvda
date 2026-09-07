# Configuration

Python services use Pydantic settings with this precedence: constructor values, environment,
local `.env`, `config.yaml`, file secrets, and defaults. Root `.env` configures Compose ports
and shared development values. Each service and PostgreSQL has a tracked `.env.example`;
real `.env` files are ignored.

All service logs are JSON and contain timestamp, logger, level, and message fields.

The Telegram scraper requires `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`,
`TELEGRAM_PHONE_NUMBER`, and `TELEGRAM_SESSION_STRING`. Local values belong in the ignored
service `.env`; deployments inject the same values from GitHub Secrets. The session string is
an authorized MTProto login secret and must be rotated if revoked.
