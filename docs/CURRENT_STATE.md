# Project Context

## Current State

The Telegram collection foundation persists an agreed fixed channel pool, raw posts and
revisions, current channel avatars, and PostgreSQL analysis jobs. A DVC-versioned `golden_v0`
annotation pilot and offline DSPy experiment area define the future semantic-extraction contract.
The API exposes service health, read-only channel collection health, and current-avatar URLs; AI
execution and the product UI remain shells.

## Service Map

| Boundary | Responsibility | Dependencies |
| --- | --- | --- |
| API | Health, collection status, and current-avatar HTTP surface | PostgreSQL, avatar volume |
| Telegram scraper | Fixed channel/post/avatar collection | PostgreSQL job handoff, avatar volume |
| AI worker | Future post analysis | PostgreSQL job handoff (future), AI provider (future) |
| Frontend | Future investigation and registry UI | API |
| monitoring-common | Settings, JSON logging, contracts | None |

## Runtime Decisions

- Docker Compose starts all services plus PostgreSQL 16.
- PostgreSQL is the lightweight queue through a leased-job table. Live collection jobs take
  priority over throttled historical backfill jobs.
- Public Telegram sources resolve through their configured handles; stored peer IDs are durable
  source identity, not standalone Telethon lookup values.
- Configuration priority is constructor arguments, environment, `.env`, `config.yaml`, then
  file secrets. See `system/foundation/configuration.md`.
- The reviewed source seed contains INSIDER UA, Україна Сейчас, Реальна війна, Україна Online,
  and Times of Ukraine. Production collection authenticates with a dedicated Telegram account.
- Current Telegram channel avatars are stored in a shared Docker volume, not PostgreSQL; their
  stable relative URLs use `/channel-images/{channel_id}` and are refreshed every collection poll.
- `golden_v0` is an offline, DVC-tracked pilot for annotation-schema validation. It does not make
  the AI worker a runtime dependency on DVC or implement DSPy inference yet.

## Documentation

The experimental annotation editor reads PostgreSQL Post Revisions in read-only transactions
and provides a Ukrainian form with evidence selection, local drafts, registry candidates, and
validated golden_v0 exports. It runs independently on localhost through experimental Compose;
see `../experiments/annotation-ui/README.md`. Production services remain unchanged.

`VISION.md` describes target capability. `system/` describes the implemented foundation. Future
work belongs in `tasks/backlog/`; operational records belong in `problems/backlog/`.
