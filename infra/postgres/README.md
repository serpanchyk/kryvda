# PostgreSQL Runtime

Copy `.env.example` to `.env` before starting Docker Compose. PostgreSQL 16 stores durable
application data and the lightweight leased-job queue. The initial schema runs from `init/` only
when PostgreSQL creates a new data volume.

The Compose `migrate` service tracks applied inference migrations in `schema_migrations` and runs
before application services. Fresh volumes receive their ledger records during initialization.
Legacy databases without the v3 registry receive the intentional `003` transition followed by
`004` through `010`; it preserves raw posts and revisions but replaces obsolete analysis jobs and
results. Back up a legacy production volume before its first Compose startup on this version.
