# Runtime

Docker Compose starts PostgreSQL, a one-shot versioned migration service, the FastAPI API, Telegram
collection worker, AI worker, LiteLLM proxy, and the built frontend. PostgreSQL is the only
stateful dependency and provides the leased job table used to hand analysis work from scraper to
AI worker. API, scraper, and worker wait for successful migrations. The scraper runs as a single
restartable instance and polls active approved channels every five minutes by default. The scraper
and API share the `channel-images` Docker volume: the scraper stores only each channel's current
Telegram avatar, and the API exposes it at `/channel-images/{channel_id}`. PostgreSQL stores its
relative URL and MIME type but no binary image data.

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

The default worker has one job task and one PostgreSQL advisory-lock provider slot. Settings can
raise bounded job, provider, and Pass 3 batch concurrency after measurement; advisory slots apply
across Compose-scaled worker containers without introducing another runtime dependency. The API exposes queue and recent-run state at `/analysis/health`, including scheduled-retry count,
the nearest retry time, and retry counts by error kind. Terminal `failed` records are retained
only as historical audit records or superseded work.

To retry a corrected terminal v3 job, reset only the selected rows:

```sql
UPDATE analysis_jobs
SET status = 'pending', attempts = 0, available_at = now(), leased_until = NULL,
    last_error_kind = NULL, last_error = NULL, updated_at = now()
WHERE id IN (<job ids>) AND status = 'failed';
```
