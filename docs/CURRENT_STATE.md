# Project Context

## Current State

The Telegram collection foundation persists an agreed fixed channel pool, raw posts and
revisions, current channel avatars, a human-maintained monitored-entity registry, inference-v3.2
jobs, pass diagnostics, candidates, claims and claim-target classifications. Production analysis
uses deterministic target filtering followed by three focused Mamay passes. The API exposes
service health, collection health, current-avatar URLs and unauthenticated registry/candidate
administration; product UI remains a shell.

## Service Map

| Boundary | Responsibility | Dependencies |
| --- | --- | --- |
| API | Health, collection status, avatars, registry and candidate review | PostgreSQL, avatar volume |
| Telegram scraper | Fixed channel/post/avatar collection and target-filtered job handoff | PostgreSQL, avatar volume |
| AI worker | Three-pass target inference and deterministic persistence | PostgreSQL, LiteLLM proxy |
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
  `MamayLM-Gemma-3-27B-IT`. Inference v3.2 sanitizes Pass 1 and individual Pass 2 claims before
  independently validating entities, claims and claim-target classifications, permits one
  contract repair per pass, and retains raw, sanitized and final payloads with categorized
  diagnostics.
- The supplied 128-entry registry seed is active and monitored. Approved aliases alone drive
  filtering and resolution. Registry expansion backfills only the latest accessible revision of
  each stored post.
- `golden_v0` is an offline, DVC-tracked pilot for annotation-schema validation. The offline Mamay
  comparison generator reuses the worker's inference request boundary to pair each golden input,
  full reviewed annotation, and Mamay output for external review. Parsed outputs that fail local
  validation are retained with their validation category; it does not score or judge the outputs
  and does not make the AI worker a runtime dependency on DVC.
- `mamay_vs_golden_v1` is a separate DVC-tracked offline comparison run for an experimental,
  reduced Mamay v2 contract. It removes model-generated character offsets and rhetorical graph
  links, projects reviewed `golden_v0` annotations into the comparable shape, and leaves the
  production extraction contract unchanged.
- `mamay_vs_golden_v2` records the full auditable inference-v3 pipeline against `golden_v0`,
  including target-filter decisions, all primary/repair outputs, final resolution and post length.
- `mamay_vs_golden_v3_1` repeats the same 55 examples with the v3.1 sanitizer, inflection-aware
  filter, reordered Pass 2 guided schema and explicit 4,096-token completion budget. Its generated
  summary compares contract-health counts with `mamay_vs_golden_v2`. The final run recorded one
  filtered post, 47 failed analyses and seven completed analyses; Pass 2 primary-valid outputs
  rose from zero to seven and JSON parse failures fell from 20 to four. The run remains an
  operational contract measurement, not a semantic-quality score.
- `mamay_vs_golden_v3_2` reruns the unchanged 55 examples with item-level Pass 2 sanitation,
  evidence realignment, mixed-group resolution, and collision-safe surname morphology. Its DVC
  summary compares recovery/drop action counts and contract-health results with v3.1. The run
  completed 46 examples (versus seven in v3.1), with zero grounding failures and 18 deterministic
  evidence realignments; it remains a contract-health measurement rather than a semantic score.

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
