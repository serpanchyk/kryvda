# Deploy the Telegram gateway to Vercel

The department server cannot reach Telegram. `apps/telegram-gateway` holds the Telegram session
and runs on Vercel's free Hobby plan; the department scraper calls it over HTTPS once an hour.
The gateway has no database and no state. See [the server guide](../../DEPLOY.md) for the other
half of the deployment.

## 1. Telegram credentials

1. Use a dedicated Telegram account, not a personal one. It must be a member of every private
   monitored channel.
2. Create an application at <https://my.telegram.org> and note `api_id` and `api_hash`.
3. Put `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE_NUMBER` in the ignored root
   `.env` and run once:

   ```bash
   uv run telegram-monitor-authorize
   ```

   Copy the printed `TELEGRAM_SESSION_STRING` value. From now on this session belongs to Vercel
   only: Telegram revokes a session (`AUTH_KEY_DUPLICATED`) used from two places at once. Local
   development must use a different session.
4. Generate the shared gateway token: `openssl rand -hex 32`.

## 2. Vercel project

1. In Vercel, **Add New → Project** and import this Git repository.
2. Set **Root Directory** to `apps/telegram-gateway`. Vercel detects FastAPI from `pyproject.toml`
   and loads `app` from `app.py`. Python 3.12, region `fra1`, and the 300-second limit come from
   `.python-version` and `vercel.json`.
3. Under **Environment Variables**, add these for the **Production** environment only:

   | Name | Value |
   | --- | --- |
   | `TELEGRAM_API_ID` | from my.telegram.org |
   | `TELEGRAM_API_HASH` | from my.telegram.org |
   | `TELEGRAM_SESSION_STRING` | from `telegram-monitor-authorize` |
   | `TELEGRAM_GATEWAY_TOKEN` | the generated token |

   Production-only is essential: preview deployments must not receive the session, or a preview
   could use it concurrently. Previews therefore fail at startup, which is expected.
4. Deploy. Pushes to the production branch redeploy the gateway only when
   `apps/telegram-gateway` or `uv.lock` changed (`ignoreCommand` in `vercel.json`).

Keep Vercel **Deployment Protection** off for the production domain (the Hobby default): the
scraper authenticates with the gateway token, and Vercel's login wall would answer it with 401.

## 3. Verify

```bash
curl https://<project>.vercel.app/health
curl -X POST https://<project>.vercel.app/v1/channels/fetch \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"channel": {"configured_reference": "insiderUKR", "access_kind": "public"},
       "include_avatar": false}'
```

The second call returns the channel identity and `head_message_id`. Then give the department
administrator `TELEGRAM_GATEWAY_URL=https://<project>.vercel.app` and the token through a private
channel.

## Operations

- **Revoked session** (scraper reports `returned 503`): generate a new session, replace
  `TELEGRAM_SESSION_STRING` in Vercel, and redeploy. Old sessions can be terminated in Telegram
  under *Settings → Devices*.
- **Rotating the token**: change `TELEGRAM_GATEWAY_TOKEN` in Vercel, redeploy, then update the
  department `.env` and run `docker compose up -d`.
- **Logs**: Vercel project → *Logs*. Each fetch logs the channel, page sizes, and duration.
- **Build cannot resolve the uv workspace**: the gateway has no workspace dependencies, so in
  *Settings → Build and Deployment* disable *Include files outside the root directory*; Vercel then
  installs from `apps/telegram-gateway/pyproject.toml` alone.

## Limits that shape the design

- Vercel Hobby: 300-second function duration, 4.5 MB response, dynamic outbound IPs, personal and
  non-commercial use. A request returns at most 500 posts per direction (200 by default).
- Each request opens and closes its own Telegram connection, and an instance serves one request
  at a time; the scraper also calls the gateway strictly sequentially.
- Telegram flood waits up to 20 seconds are slept through; longer ones return HTTP 429 and the
  scraper stops that collection run.
