# PostgreSQL Runtime

Copy `.env.example` to `.env` before starting Docker Compose. PostgreSQL 16 stores durable
application data and will later provide the lightweight leased-job queue. No application
schema or initialization SQL is included in the foundation.
