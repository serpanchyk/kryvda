# Configuration

Python services use Pydantic settings with this precedence: constructor values, environment,
local `.env`, `config.yaml`, file secrets, and defaults. Root `.env` configures Compose ports
and shared development values. Each service and PostgreSQL has a tracked `.env.example`;
real `.env` files are ignored.

All service logs are JSON and contain timestamp, logger, level, and message fields.
