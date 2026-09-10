# Configuration

Python services use Pydantic settings with this precedence: constructor values, environment,
local `.env`, `config.yaml`, file secrets, and defaults. Root `.env` configures Compose ports
and shared development values. Each service and PostgreSQL has a tracked `.env.example`;
real `.env` files are ignored.

All service logs are JSON and contain timestamp, logger, level, and message fields.

The Telegram scraper requires `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`,
`TELEGRAM_PHONE_NUMBER`, and `TELEGRAM_SESSION_STRING`. Local values belong in the ignored
root `.env`; deployments inject the same values from GitHub Secrets. The session string is
an authorized MTProto login secret and must be rotated if revoked.

## LiteLLM proxy

The internal LiteLLM proxy requires `LAPATHONIIA_API_KEY`, an upstream API key authorized for
`MamayLM-Gemma-3-27B-IT`, and `LITELLM_MASTER_KEY`, a separate random secret used by callers of
the proxy. `LAPATHONIIA_API_BASE` defaults to `https://api.lapathoniia.top` and is retained as an
environment setting only for an upstream endpoint migration. Keep all three values in the ignored
root `.env` locally and in the deployment secret store outside development.

Compose does not publish the proxy port. Compose services call it at `http://litellm:4000` and
authenticate using `LITELLM_MASTER_KEY`; that key is never forwarded upstream. The proxy sends
`LAPATHONIIA_API_KEY` only to the upstream API.

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

Set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE_NUMBER` in the ignored root
`.env`, then run this once from the repository root:

```bash
uv run telegram-monitor-authorize
```

The command requests the Telegram verification code and, if enabled, the two-step verification
password. It writes a single `TELEGRAM_SESSION_STRING=...` line only to the terminal; copy that
value to the ignored root `.env` for Docker Compose and to the production secret store. Never
commit it or send it in chat. Use the dedicated project account for production.
