# Runtime

Docker Compose starts PostgreSQL, the FastAPI API, Telegram collection worker, AI worker,
and the built frontend. PostgreSQL is the only stateful dependency and provides the leased-job
table used to hand analysis work from scraper to AI worker. The scraper runs as a single
restartable instance and polls active approved channels every five minutes by default.
