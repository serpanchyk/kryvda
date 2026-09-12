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

Existing databases must apply `infra/postgres/migrations/003_inference_v3.sql` with `psql`. The
migration intentionally removes v1 analysis jobs/results, preserves raw posts and revisions, seeds
the supplied monitored registry, and enqueues matching latest historical revisions.
Apply `infra/postgres/migrations/004_inference_v3_1.sql` after it to add the v3.1 sanitized and
final per-pass diagnostic fields without replacing the three-pass schema.

Registry and candidate-review endpoints are currently unauthenticated. Keep the API behind trusted
deployment network controls until authentication is added.

## Local Checks

```bash
uv lock
uv sync --frozen --all-packages
uv run pre-commit run --all-files
uv run pytest
(cd apps/frontend && npm ci && npm run lint && npm run test && npm run build)
```
