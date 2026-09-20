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

Compose runs the versioned `migrate` service before API, scraper, and AI worker startup. Fresh
volumes are marked at v3.5.2 by their initialization scripts. For an existing legacy volume the
service detects the missing v3 registry schema, applies migrations `003` through `010`, preserves
raw posts/revisions, and re-enqueues matching latest revisions. Migration `003` intentionally
replaces obsolete analysis jobs/results; take a PostgreSQL backup before the first legacy upgrade.

Inspect migration output with:

```bash
docker compose logs migrate
```

The AI worker defaults to one job and one provider request at a time. Benchmark queue throughput
and provider errors before raising `ANALYSIS_CONCURRENCY`, `LLM_MAX_CONCURRENCY`, or
`ANALYSIS_CLASSIFICATION_CONCURRENCY` in `.env`.

Run the opt-in PostgreSQL pipeline smoke test against an isolated migrated database with:

```bash
INTEGRATION_POSTGRES_DSN=postgresql://... uv run pytest \
  apps/ai-worker/tests/integration/test_postgres_pipeline.py
```

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
