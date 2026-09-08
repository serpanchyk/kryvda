# PostgreSQL Runtime

Copy `.env.example` to `.env` before starting Docker Compose. PostgreSQL 16 stores durable
application data and the lightweight leased-job queue. The initial schema runs from `init/` only
when PostgreSQL creates a new data volume.

Apply scripts in `migrations/` to an existing volume before deploying the related application
change. They are idempotent so local development can safely rerun them.
