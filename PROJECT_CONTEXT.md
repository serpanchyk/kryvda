# Project Context

## Current State

The Telegram collection foundation persists an agreed fixed channel pool, raw posts and
revisions, and PostgreSQL analysis jobs. The API exposes service health and read-only channel
collection health; AI execution and the product UI remain shells.

## Service Map

| Boundary | Responsibility | Dependencies |
| --- | --- | --- |
| API | Health and collection-status HTTP surface | PostgreSQL |
| Telegram scraper | Fixed channel/post collection | PostgreSQL job handoff |
| AI worker | Future post analysis | PostgreSQL job handoff (future), AI provider (future) |
| Frontend | Future investigation and registry UI | API |
| monitoring-common | Settings, JSON logging, contracts | None |

## Runtime Decisions

- Docker Compose starts all services plus PostgreSQL 16.
- PostgreSQL is the lightweight queue through a leased-job table. Live collection jobs take
  priority over throttled historical backfill jobs.
- Configuration priority is constructor arguments, environment, `.env`, `config.yaml`, then
  file secrets. See `docs/system/foundation/configuration.md`.

## Documentation

`docs/VISION.md` describes target capability. `docs/system/` describes the implemented
foundation. Future work belongs in `docs/tasks/backlog/`; operational records belong in
`docs/problems/backlog/`.
