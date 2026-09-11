# Project Context

## Current State

The Telegram collection foundation persists an agreed fixed channel pool, raw posts and
revisions, current channel avatars, PostgreSQL analysis jobs, and validated candidate extraction
results. A DVC-versioned `golden_v0` annotation pilot and the shared `extraction_schema_v1`
candidate-extraction contract define the semantic-extraction boundary. The API exposes service
health, read-only channel collection health, and current-avatar URLs; product UI remains a shell.

## Service Map

| Boundary | Responsibility | Dependencies |
| --- | --- | --- |
| API | Health, collection status, and current-avatar HTTP surface | PostgreSQL, avatar volume |
| Telegram scraper | Fixed channel/post/avatar collection | PostgreSQL job handoff, avatar volume |
| AI worker | Candidate extraction from Post Revisions | PostgreSQL job handoff, LiteLLM proxy |
| LiteLLM proxy | Internal OpenAI-compatible model gateway | Lapathoniia AI API |
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
- LiteLLM provides the internal-only OpenAI-compatible endpoint `http://litellm:4000` for
  `MamayLM-Gemma-3-27B-IT`, forwarding to the Lapathoniia AI API. The AI worker requests strict
  JSON-Schema output, validates text-grounded extraction locally, and persists one immutable
  candidate result per Post Revision.
- `golden_v0` is an offline, DVC-tracked pilot for annotation-schema validation. The offline Mamay
  comparison generator reuses the worker's inference request boundary to pair each golden input,
  full reviewed annotation, and Mamay output for external review. Parsed outputs that fail local
  validation are retained with their validation category; it does not score or judge the outputs
  and does not make the AI worker a runtime dependency on DVC.
- `mamay_vs_golden_v1` is a separate DVC-tracked offline comparison run for an experimental,
  reduced Mamay v2 contract. It removes model-generated character offsets and rhetorical graph
  links, projects reviewed `golden_v0` annotations into the comparable shape, and leaves the
  production extraction contract unchanged.

## Documentation

The experimental annotation editor reads PostgreSQL Post Revisions in read-only transactions
and provides a Ukrainian form or mutable-JSON import, evidence selection, local drafts, registry
candidates, and validated golden_v0 exports. JSON import copies a frozen post and a constrained
schema, then opens an editable unsaved preview. Confirmation runs protected validation and only
then adds new canonical names as local candidate registry entries. It runs independently on
localhost through experimental Compose; see `../experiments/annotation-ui/README.md`. Production
services remain unchanged.

`VISION.md` describes target capability. `system/` describes the implemented foundation. Future
work belongs in `tasks/backlog/`; operational records belong in `problems/backlog/`.
