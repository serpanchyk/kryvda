# Runtime

Docker Compose starts PostgreSQL, the FastAPI API, Telegram collection worker, AI worker, LiteLLM
proxy, and the built frontend. PostgreSQL is the only stateful dependency and provides the leased
job table used to hand analysis work from scraper to AI worker. The scraper runs as a single
restartable instance and polls active approved channels every five minutes by default. The scraper
and API share the `channel-images` Docker volume: the scraper stores only each channel's current
Telegram avatar, and the API exposes it at `/channel-images/{channel_id}`. PostgreSQL stores its
relative URL and MIME type but no binary image data.

LiteLLM is an internal-only, stateless model gateway. It is available only as
`http://litellm:4000` on the Compose network and exposes the OpenAI-compatible
`MamayLM-Gemma-3-27B-IT` model. It has no PostgreSQL dependency. The AI worker leases one job at
a time with `FOR UPDATE SKIP LOCKED`, prioritizes live collection over backfill, and requests a
three strict JSON-Schema passes. The worker renews its five-minute lease before each two-minute
request. Transient gateway failures retry up to three job attempts and reuse validated passes;
contract failures receive one repair inference and then become terminal. Raw attempts are durable.

To retry a corrected terminal v3 job, reset only the selected rows:

```sql
UPDATE analysis_jobs
SET status = 'pending', attempts = 0, available_at = now(), leased_until = NULL,
    last_error_kind = NULL, last_error = NULL, updated_at = now()
WHERE id IN (<job ids>) AND status = 'failed';
```
