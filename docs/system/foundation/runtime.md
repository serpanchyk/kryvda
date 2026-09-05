# Runtime

Docker Compose starts PostgreSQL, the FastAPI API shell, Telegram scraper shell, AI worker
shell, and the built frontend. PostgreSQL is the only stateful dependency. A later migration
will introduce the leased-job table used to hand work from scraper to AI worker.
