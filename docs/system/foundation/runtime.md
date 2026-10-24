# Runtime

The system runs in two places. The department server runs Docker Compose: PostgreSQL, a one-shot
versioned migration service, a daily backup service, the FastAPI API, Telegram collection worker,
AI worker, LiteLLM proxy, and the built frontend. The department network blocks Telegram, so the
stateless Telegram gateway runs on Vercel and is the only component that talks MTProto; the
scraper reaches it with outbound HTTPS only. Locally, the `telegram` Compose profile runs the same
gateway as a container.

PostgreSQL is the only stateful dependency and provides the leased job table used to hand analysis
work from scraper to AI worker. API, scraper, and worker wait for successful migrations; every
long-running service restarts automatically. The scraper runs as a single restartable instance and
collects active approved channels hourly by default. For each channel it calls
`POST /v1/channels/fetch` page by page, strictly sequentially: the first page returns identity and
avatar, each page returns up to 200 live posts after the live cursor and up to 200 historical
posts within the one-year backfill window. The first live page of each run starts before the last
`COLLECTION_REFRESH_HOURS` (48 by default), so recent edits become new revisions and stored
metadata is refreshed; only a changed text enqueues analysis. Live posts are caught up within a
run; history arrives over several runs within a budget of 10 pages per channel. Post metadata
records the forward origin (peer, original message, date, sender labels) when Telegram provides it. A Telegram flood wait longer than
20 seconds returns HTTP 429 and ends the run. The gateway opens and closes one Telegram connection
per request and never serves two requests at once, so the session is never used concurrently.

The scraper and API share the `channel-images` Docker volume: the scraper stores only each
channel's current Telegram avatar, and the API exposes it at `/channel-images/{channel_id}`.
PostgreSQL stores its relative URL and MIME type but no binary image data. Browsers reach the API
through the frontend nginx at `/api/`, which forwards only `GET` requests.

LiteLLM is an internal-only, stateless model gateway. It is available only as
`http://litellm:4000` on the Compose network and exposes the OpenAI-compatible
`MamayLM-Gemma-3-27B-IT` model. It has no PostgreSQL dependency. The AI worker leases one job at
a time with `FOR UPDATE SKIP LOCKED`, prioritizes live collection over backfill, and requests three
strict JSON-Schema passes. Default output budgets are 1,024 tokens for entities, 4,096 for claims,
and a classification budget capped at 1,024 tokens that scales with batch size. The worker renews
its five-minute lease before each two-minute
request. Every execution error, including provider, JSON/schema, and internal errors, retains
validated passes and is retried indefinitely. The first rapid retries wait 5 and 10 seconds;
subsequent attempts use 5 minutes, 30 minutes, 2 hours, 6 hours, then a 24-hour cap with
deterministic 0–10% jitter. Expired leases follow the same scheduled-retry lifecycle. New live
jobs always lease before due backfill and scheduled retries. Raw attempts, sanitized payloads,
validation errors, provider finish metadata and final per-pass outcomes are durable.

The Compose worker runs 16 job tasks and 16 PostgreSQL advisory-lock provider slots; Pass 3
batch concurrency stays 1. Advisory slots apply across Compose-scaled worker containers without
introducing another runtime dependency. A revision may be analyzed again after an inference
change; the newer completed run marks the earlier completed run `superseded`, and analytics read
only completed statuses. The API exposes queue and recent-run state at `/analysis/health`, including scheduled-retry count,
the nearest retry time, and retry counts by error kind. `/system/activity?days=N` (1..90,
default 30) returns read-only, zero-filled Kyiv-day collection and run-outcome series, the last 48
UTC hours of run outcomes, per-pass reliability and latency percentiles, model and pipeline-version
usage, per-channel collection series, and window totals (including the median duration of plain
`completed` runs) for the «Система» page. Terminal `failed` records are retained
only as historical audit records or superseded work.

To retry a corrected terminal v3 job, reset only the selected rows:

```sql
UPDATE analysis_jobs
SET status = 'pending', attempts = 0, available_at = now(), leased_until = NULL,
    last_error_kind = NULL, last_error = NULL, updated_at = now()
WHERE id IN (<job ids>) AND status = 'failed';
```

## Mac mini Kubernetes

The optional `k8s/` runtime uses Argo CD/Kustomize and GitHub Actions GHCR images.
PostgreSQL runs on mac-master; API and the single Recreate scraper share a local-path
avatar PVC on mac-node1; daily backup dumps use a PVC on mac-node2. This topology
provides persistence, not failover. Database init SQL is packaged with migrations;
a Sync hook gates application rollout. API readiness checks the database schema,
while liveness checks only HTTP. Frontend retains the read-only API proxy.
Secrets are sealed for the target cluster; plain Secret templates and the bootstrap
Application are excluded from the managed resource list. See the deployment runbook.
