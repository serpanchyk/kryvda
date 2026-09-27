# Project Context

## Current State

Кривда persists an agreed fixed channel pool, raw posts and
revisions, current channel avatars, a human-maintained monitored-entity registry, inference-v3.5.1
jobs, pass diagnostics, candidates, claims and claim-target classifications. Production analysis
uses deterministic target filtering followed by three focused Mamay passes. The API exposes
service health, collection health, current-avatar URLs, unauthenticated registry/candidate
administration, and read-only investigation aggregates. The product UI provides an operational
dashboard, a full entity registry, channel comparison, evidence drill-down, and source-post detail.
The Ukrainian UI uses the Кривда brand, shared date ranges, searchable aliases, and read-only
pipeline and claim analytics; registry mutations remain outside the UI.

## Service Map

| Boundary | Responsibility | Dependencies |
| --- | --- | --- |
| API | Health, collection status, avatars, registry review and read-only investigation data | PostgreSQL, avatar volume |
| Telegram scraper | Fixed channel/post/avatar collection and target-filtered job handoff | PostgreSQL, avatar volume |
| AI worker | Three-pass target inference and deterministic persistence | PostgreSQL, LiteLLM proxy |
| LiteLLM proxy | Internal OpenAI-compatible model gateway | Lapathoniia AI API |
| Frontend | Кривда dashboard, entity/channel analysis, claims and source-post evidence | API |
| monitoring-common | Settings, JSON logging, contracts | None |

## Runtime Decisions

- Docker Compose starts PostgreSQL, a versioned migration gate, then all application services.
- PostgreSQL migration state is stored in `schema_migrations`; fresh initialization records the
  v3.5.2 baseline and the v3 pass-attempt uniqueness repair, while a legacy schema is upgraded
  through the v3 transition automatically.
- PostgreSQL is the lightweight queue through a leased-job table. New live collection jobs take
  priority over throttled historical backfill and due scheduled retries. Every analysis error and
  expired lease becomes a durable retry: after the rapid 5- and 10-second retries, the worker uses
  5 minutes, 30 minutes, 2 hours, 6 hours, then a jittered 24-hour cadence indefinitely. Terminal
  failures are retained only as historical or superseded audit records.
- Public Telegram sources resolve through their configured handles; stored peer IDs are durable
  source identity, not standalone Telethon lookup values. Private sources restore their Telegram
  access metadata from the dedicated account's dialogs and are collected only while that account
  remains a member.
- Configuration priority is constructor arguments, environment, `.env`, `config.yaml`, then
  file secrets. See `system/foundation/configuration.md`.
- The reviewed source seed contains INSIDER UA, Україна Сейчас, Реальна війна, Україна Online,
  and Times of Ukraine. Production collection authenticates with a dedicated Telegram account.
- Current Telegram channel avatars are stored in a shared Docker volume, not PostgreSQL; their
  stable relative URLs use `/channel-images/{channel_id}` and are refreshed every collection poll.
- LiteLLM provides the internal-only OpenAI-compatible endpoint `http://litellm:4000` for
  `MamayLM-Gemma-3-27B-IT`. Inference v3.5.1 preserves v3.5 reliability and three-pass topology,
  removes the ambiguous bare `ЧЕСНО` alias, defaults unanchored Pass 2 claims to
  `channel_editorial`, and prevents Pass 3 from treating a reported attack on a target as the
  channel's negative stance toward that target.
- The supplied 128-entry registry seed is active and monitored. Approved aliases alone drive
  filtering and resolution. Registry expansion backfills only the latest accessible revision of
  each stored post.
- The AI worker supports bounded PostgreSQL-coordinated job/provider/classification concurrency,
  but Compose defaults remain one job and one provider request until throughput benchmarks justify
  an increase. API `/analysis/health` exposes queue and recent-run operational state.
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
- `mamay_vs_golden_v3_3` reruns the unchanged 55 examples with prefilter entity fallback,
  attribution normalization, and pair-level classification retries. The completed run reached
  final output for all 55 posts: 42 completed, 12 partial classifications, and one entity
  fallback; it recorded 18 attribution sanitizations and 120 permanently missing pairs.
- `mamay_vs_golden_v3_4` uses the same 55 examples with bounded Pass 3 batches and hierarchical
  pair recovery. Its DVC artifact preserves the raw batch and individual-retry audit trail.
- `mamay_vs_golden_v3_5` uses the same runner and input with the v3.5 semantic prompts and
  deterministic non-negative-rhetoric sanitation; its summary compares contract-health metrics
  with the preserved v3.4 artifact. `mamay_vs_golden_v3_5_1` is a DVC-tracked standalone run over
  the current 100-post annotated dataset. Its summary intentionally has no numeric baseline,
  because the preserved v3.5 artifact contains only 55 examples.
- Inference v3.5.2 preserves the v3.5.1 reliability path and makes two semantic changes: `Рух
  ЧЕСНО` accepts its uppercase acronym only as an exact organization reference, and Pass 3 makes
  stance attribution-aware so adverse events, polls, and another actor's attack are not treated as
  the current perspective's negative stance. The 100-example report is canonical-only and labels
  its tuned partitions `old55`, `diagnostic45`, and `all100`; `mixed` stance and `denied`
  epistemics remain `unresolved_legacy` and are excluded from their respective metrics.
- `registry_post_coverage` is a DVC-tracked snapshot of the number of latest accessible posts
  matching each active registry entity under the production alias policy. Its summary records the
  live queue and a throughput-based ETA; it is an operational snapshot, not a model evaluation.

## Documentation

The Kryvda investigation UI uses an editorial newsroom layout with a responsive top masthead,
self-contained visualization sections, Kyiv Type Serif headlines, and Fixel Text data typography.
The overview leads with negative classifications, temporal activity, attacked-entity rankings,
channel comparisons, and auditable claims. Entity profiles add stance-over-time, epistemic-status,
and attribution distributions. Their URL-backed global filters distinguish publication channel from
claim attribution, including channel position, quoted-source, source-kind, and stable named-source
registry identity filters; every Entity aggregate and its evidence feed shares that scope. Select controls use
Ukrainian visible labels and responsive, wrapping menus; Entity filters group primary controls separately from
expandable additional analytical controls. Channel rows now open `/channels/{id}` profiles with activity,
stance, entity, rhetoric, epistemic, attribution, and recent-claim analysis. Post detail uses a
source/analysis split view and exposes evidence, target, stance, rhetoric, epistemic status, and
attribution for every extracted claim.

Analytical lists use server-side offset pagination (25 records by default). Registry aliases remain
search-only internal data and are never included in analytical responses. The shared 7, 30, and
90-day presets, all-time option, and custom inclusive calendar range are encoded in the URL and
preserved across top-level navigation. Entity and channel chart selections are also URL-backed and
filter their evidence or claims. Entity analytics excludes the technical `відсутнє` classification
from its evaluative totals. Rhetoric shares count assigned labels, while epistemic and attribution
shares count distinct claims; the interface labels these denominators explicitly.

The production frontend nginx configuration falls back to `index.html` for unknown paths so
browser refreshes and direct links to React Router routes such as `/entities/{id}` remain valid.

The experimental annotation editor reads PostgreSQL Post Revisions in read-only transactions
and provides a Ukrainian form or mutable-JSON import, evidence selection, local drafts, registry
candidates, and validated golden_v0 exports. JSON import copies a frozen post and a constrained
schema, then opens an editable unsaved preview. Confirmation runs protected validation and only
then adds new canonical names as local candidate registry entries. It runs independently on
localhost through experimental Compose; see `../experiments/annotation-ui/README.md`. Production
services remain unchanged.

`VISION.md` describes target capability. `system/` describes the implemented foundation. Future
work belongs in `tasks/backlog/`; operational records belong in `problems/backlog/`.
