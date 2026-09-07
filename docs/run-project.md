# Run the Project

## Docker Compose

```bash
cp .env.example .env
cp infra/postgres/.env.example infra/postgres/.env
uv run telegram-monitor-authorize
docker compose up --build
```

Before authorization, add `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and
`TELEGRAM_PHONE_NUMBER` to the ignored root `.env`. Copy the printed session-string assignment
back into that file before starting Compose. The database seeds the approved public sources on
its first initialization.

The API health endpoint is `http://localhost:8000/health`; the frontend is
`http://localhost:5173`.

## Local Checks

```bash
uv lock
uv sync --frozen --all-packages
uv run pre-commit run --all-files
uv run pytest
(cd apps/frontend && npm ci && npm run lint && npm run test && npm run build)
```
