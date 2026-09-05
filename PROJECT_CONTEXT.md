# Project Context

## Current State

Only the runnable repository foundation exists. API, scraper, and AI worker processes boot;
the API exposes `/health`; the frontend is a Vite shell. No product pipeline or persistence
schema exists yet.

## Service Map

| Boundary | Responsibility | Dependencies |
| --- | --- | --- |
| API | Future read/write HTTP surface | PostgreSQL (future) |
| Telegram scraper | Future channel/post collection | PostgreSQL job handoff (future) |
| AI worker | Future post analysis | PostgreSQL job handoff (future), AI provider (future) |
| Frontend | Future investigation and registry UI | API |
| monitoring-common | Settings, JSON logging, contracts | None |

## Runtime Decisions

- Docker Compose starts all services plus PostgreSQL 16.
- PostgreSQL will become the lightweight queue through a leased-job table; no queue table or
  implementation is present at this stage.
- Configuration priority is constructor arguments, environment, `.env`, `config.yaml`, then
  file secrets. See `docs/system/foundation/configuration.md`.

## Documentation

`docs/VISION.md` describes target capability. `docs/system/` describes the implemented
foundation. Future work belongs in `docs/tasks/backlog/`; operational records belong in
`docs/problems/backlog/`.
