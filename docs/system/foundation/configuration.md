# Configuration

Python services use Pydantic settings with this precedence: constructor values, environment,
local `.env`, `config.yaml`, file secrets, and defaults. The single root `.env` configures every
Compose service, including PostgreSQL; `.env.example` marks the five values a server needs
(`POSTGRES_PASSWORD`, `LAPATHONIIA_API_KEY`, `LITELLM_MASTER_KEY`, `TELEGRAM_GATEWAY_URL`,
`TELEGRAM_GATEWAY_TOKEN`), and Compose refuses to start without them. Each service also keeps a
tracked `.env.example` for running it outside Compose; real `.env` files are ignored.

All service logs are JSON and contain timestamp, logger, level, and message fields.

The frontend calls the API on its own origin under `/api`; its nginx proxies `GET` requests to the
API, so no API address is built into the bundle. `VITE_API_BASE_URL` overrides this only for
special setups. The API's `FRONTEND_ALLOWED_ORIGIN` CORS setting matters only for such cross-origin
use.

## Telegram gateway and scraper

Only the Telegram gateway holds Telegram credentials: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`,
`TELEGRAM_SESSION_STRING`, and the shared `TELEGRAM_GATEWAY_TOKEN` (at least 32 characters).
`TELEGRAM_FLOOD_SLEEP_THRESHOLD_SECONDS` (20 by default) bounds how long it sleeps through a
Telegram flood wait before returning HTTP 429. In production these are Production-only Vercel
environment variables; locally Compose passes them from the root `.env` to the
`telegram-gateway` service of the `telegram` profile. The session string is an authorized MTProto
login secret, must be used by one deployment only, and must be rotated if revoked.

The scraper needs only `TELEGRAM_GATEWAY_URL` and the same `TELEGRAM_GATEWAY_TOKEN`. Its tunables
are `COLLECTION_POLL_INTERVAL_SECONDS` (3600), `COLLECTION_PAGE_SIZE` (200 posts per gateway
request, at most 500), `COLLECTION_MAX_PAGES_PER_CHANNEL` (10 requests per channel per run), and
`TELEGRAM_GATEWAY_TIMEOUT_SECONDS` (330, above Vercel's 300-second function limit).

## Operations

Compose rotates every container's JSON log at 10 MB × 5 files. The `backup` service dumps
PostgreSQL daily to `./backups` and keeps `BACKUP_RETENTION_DAYS` (14) days of dumps. PostgreSQL
and the API are published on host loopback only; `FRONTEND_PORT` (80) is the only public port.

## LiteLLM proxy

The internal LiteLLM proxy requires `LAPATHONIIA_API_KEY`, an upstream API key authorized for
`MamayLM-Gemma-3-27B-IT`, and `LITELLM_MASTER_KEY`, a separate random secret used by callers of
the proxy. `LAPATHONIIA_API_BASE` defaults to `https://api.lapathoniia.top` and is retained as an
environment setting only for an upstream endpoint migration. Keep all three values in the ignored
root `.env` locally and in the deployment secret store outside development.

Compose does not publish the proxy port. Compose services call it at `http://litellm:4000` and
authenticate using `LITELLM_MASTER_KEY`; that key is never forwarded upstream. The proxy sends
`LAPATHONIIA_API_KEY` only to the upstream API.

The AI worker receives that same secret as `LITELLM_API_KEY`. Its configurable runtime values are
`LITELLM_BASE_URL`, `ANALYSIS_MODEL`, `ANALYSIS_POLL_INTERVAL_SECONDS`,
`ANALYSIS_LEASE_SECONDS`, `ANALYSIS_REQUEST_TIMEOUT_SECONDS`, `ANALYSIS_MAX_OUTPUT_TOKENS`, and
`ANALYSIS_MAX_ATTEMPTS`. Defaults are the internal proxy, MamayLM-Gemma-3-27B-IT, 5 seconds,
300 seconds, 120 seconds, 4,096 tokens, and 3 respectively. `ANALYSIS_MAX_ATTEMPTS` controls
only rapid attempts: the initial lease followed by 5- and 10-second retries. Every later error is
scheduled for durable background recovery and is not terminal because it exceeded this setting.

An internal client uses the standard OpenAI SDK interface:

```python
from openai import OpenAI

client = OpenAI(api_key="<LITELLM_MASTER_KEY>", base_url="http://litellm:4000")
response = client.chat.completions.create(
    model="MamayLM-Gemma-3-27B-IT",
    messages=[{"role": "user", "content": "Привіт! Розкажи про Україну"}],
    temperature=0.7,
    max_tokens=1000,
)
```

## Creating the Telegram session

The command belongs to the Telegram gateway package. Set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`,
and `TELEGRAM_PHONE_NUMBER` in the ignored root `.env`, then run this once from the repository
root:

```bash
uv run telegram-monitor-authorize
```

The command requests the Telegram verification code and, if enabled, the two-step verification
password. It writes a single `TELEGRAM_SESSION_STRING=...` line only to the terminal; copy that
value to the ignored root `.env` for local Compose, or to the gateway's Production environment on
Vercel. Never commit it or send it in chat, and never use one session in both places. Use the
dedicated project account for production.
