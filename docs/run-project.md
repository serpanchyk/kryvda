# Run the Project

## Docker Compose

```bash
cp .env.example .env
uv run telegram-monitor-authorize
docker compose up -d --build
```

All Compose settings live in the single root `.env`. Fill in its required values and enable the
local-development block: `COMPOSE_PROFILES=telegram` starts the `telegram-gateway` service, and
`TELEGRAM_GATEWAY_URL=http://telegram-gateway:8080` points the scraper at it. Before
authorization, add `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE_NUMBER` of a
development account; copy the printed session-string assignment back into `.env`. Never reuse the
production gateway session locally: Telegram revokes an authorization key used from two hosts at
once (`AUTH_KEY_DUPLICATED`), which is what stopped local collection on 2026-10-07 when the same
session also ran on Vercel. Third-party clients receive login codes only inside an official
Telegram app signed in to the account, and Telegram sometimes withholds them; if no code arrives,
run `uv run telegram-monitor-authorize --qr` and scan the terminal QR code in that app
(Settings → Devices → Link Desktop Device). The database seeds the approved public sources on its
first initialization.

The API health endpoint is `http://localhost:8000/health`; the frontend listens on
`FRONTEND_PORT` and proxies `/api/` to the API. For `npm run dev`, Vite proxies `/api` to
`http://localhost:8000`.

Production deployment is documented in `DEPLOY.md` (department server) and
`docs/deploy/telegram-gateway-vercel.md` (Telegram gateway).

Compose runs the versioned `migrate` service before API, scraper, and AI worker startup. Fresh
volumes are marked at v3.7 by their initialization scripts. For an existing legacy volume the
service detects the missing v3 registry schema, applies migrations `003` through `014`, preserves
raw posts/revisions, and re-enqueues matching latest revisions. Migration `003` intentionally
replaces obsolete analysis jobs/results; take a PostgreSQL backup before the first legacy upgrade.

Inspect migration output with:

```bash
docker compose logs migrate
```

The AI worker runs 16 jobs and at most 16 concurrent provider requests by default
(`ANALYSIS_CONCURRENCY`, `LLM_MAX_CONCURRENCY`). A benchmark on 2026-10-09 ran 8 concurrent
requests per process without provider errors at about five times the single-request throughput.
`ANALYSIS_CLASSIFICATION_CONCURRENCY` stays 1 because Pass 3 batches share the same provider slots.

After an inference version change, re-analyze stored posts with the matching maintenance script.
Live jobs keep priority; each finished run supersedes the previous result of its revision, so
analytics never count both:

```bash
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < infra/postgres/maintenance/reanalyze_before_v3_7.sql
```

The scraper re-reads posts from the last `COLLECTION_REFRESH_HOURS` (48 by default) on every run,
so recent edits and current Telegram metadata are recorded. To re-read the whole one-year history
once, for example after the gateway started returning new metadata, reset the backfill cursors;
the history then arrives over the following hourly runs:

```bash
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < infra/postgres/maintenance/refresh_collected_history.sql
```

Run the opt-in PostgreSQL pipeline smoke test against an isolated migrated database with:

```bash
INTEGRATION_POSTGRES_DSN=postgresql://... uv run pytest \
  apps/ai-worker/tests/integration/test_postgres_pipeline.py
```

Registry and candidate-review endpoints are currently unauthenticated. Compose publishes the API
only on host loopback, and the frontend proxy forwards only `GET` requests, so mutations are
possible only from the server itself until authentication is added.

## Local Checks

```bash
uv lock
uv sync --frozen --all-packages
uv run pre-commit run --all-files
uv run pytest
(cd apps/frontend && npm ci && npm run lint && npm run test && npm run build)
```
