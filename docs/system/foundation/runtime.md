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
`MamayLM-Gemma-3-27B-IT` model. It has no PostgreSQL dependency and is not called by the current
AI-worker shell; adding analysis behavior requires a separate implementation decision.
