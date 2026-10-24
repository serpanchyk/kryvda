# Project Context

## Current State

Кривда persists an agreed fixed channel pool, raw posts and
revisions, current channel avatars, a human-maintained monitored-entity registry, inference-v3.6
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
| Telegram scraper | Fixed channel/post/avatar collection and target-filtered job handoff | PostgreSQL, avatar volume, Telegram gateway |
| Telegram gateway | Stateless Telegram MTProto access on Vercel, outside the department firewall | Telegram |
| AI worker | Three-pass target inference and deterministic persistence | PostgreSQL, LiteLLM proxy |
| LiteLLM proxy | Internal OpenAI-compatible model gateway | Lapathoniia AI API |
| Frontend | Кривда dashboard, entity/channel analysis, claims and source-post evidence | API |
| monitoring-common | Settings, JSON logging, contracts | None |

## Runtime Decisions

- Production is split across two hosts. The department server, which cannot reach Telegram, runs
  the Docker Compose stack started by one `docker compose up -d --build` from a git checkout
  (`DEPLOY.md`). The Telegram gateway (`apps/telegram-gateway`) runs on Vercel Hobby and holds the
  only Telegram session; the scraper calls it hourly over HTTPS with a shared Bearer token and
  pages each channel through `POST /v1/channels/fetch`. Locally the `telegram` Compose profile runs
  the same gateway as a container. Every run re-reads the last `COLLECTION_REFRESH_HOURS` (48) of
  posts, so later edits become new revisions (only changed text is re-analyzed) and stored metadata
  is refreshed; post metadata includes the forward origin when Telegram provides it. A maintenance
  script re-reads the whole one-year history once.
- One root `.env` configures the whole stack; Compose refuses to start without its five required
  values. Only the frontend port is public: PostgreSQL and the API bind to host loopback, and the
  frontend nginx proxies read-only `GET` requests to the API under `/api/`. Containers restart
  automatically, logs rotate, and a `backup` service writes daily `pg_dump` files to `./backups`.
- Docker Compose starts PostgreSQL, a versioned migration gate, then all application services.
- The API shares one bounded PostgreSQL pool (`POSTGRES_POOL_MAX_SIZE`, default 10) across all
  requests, and the frontend nginx re-resolves the API container through Docker DNS.
- PostgreSQL migration state is stored in `schema_migrations`; fresh initialization records the
  v3.5.2 baseline and the v3 pass-attempt uniqueness repair, while a legacy schema is upgraded
  through the v3 transition automatically. Fresh volumes used to record that repair without
  creating its unique index, so every analysis failed on the attempt upsert; migration 017
  creates the index wherever it is missing.
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
  each stored post. Migration 015 adds 896 aliases (Russian names, abbreviations, colloquial
  names, nicknames, insults and collective forms; `experiments/registry_aliases`), raising
  golden test-split mention recall from 86.5% to 99.0% and the share of sampled stored posts
  that pass the prefilter from 27% to 38%. One alias may now name several entities; the
  candidates pass picks the one a post means, and the implicit person surname comes only from
  the canonical name. The migration does not enqueue re-analysis of stored posts.
- The AI worker runs 16 jobs with at most 16 PostgreSQL-coordinated provider requests; Pass 3
  batch concurrency stays 1. A 2026-10-09 benchmark ran 8 concurrent requests per process without
  provider errors at about five times the single-request throughput. API `/analysis/health`
  exposes queue and recent-run operational state.
- API `GET /system/activity?days=30` (`days` 1..90, otherwise 422) is the read-only source for
  the «Система» page. For a window of `Europe/Kyiv` days ending today it returns zero-filled
  `days` (collected posts by `raw_posts.created_at`, published posts by `published_at`, run
  outcomes by `completed_at`: completed, partial, fallback, failed, filtered out), `hours` (the
  last 48 UTC hours of successful and failed runs), `passes` (attempts, repairs, invalid,
  failed, median/p95 duration and median completion tokens per inference pass), `models` (runs
  per model and pipeline version, most runs first), `channels` (collected posts per monitored
  channel per day) and `totals` (finished runs, mean `completed_at - created_at`, the median of
  that duration over plain `completed` runs, claims of runs finished in the window). A
  `superseded` run counts as completed work; any non-first attempt (`repair`, `retry`,
  `batch_retry`, `individual_retry`) counts as a repair. A run row is reused across job retries,
  so its duration includes retry waits and the mean is outlier-sensitive; read the median for
  typical run time.
- Inference v3.6 rewrites the three prompts after a manual review of 200 production posts: Pass 2
  no longer makes a speaker the target of claims that are not about it, extracts evaluative
  editorial claims (labels, sarcasm, ironic quotes, rhetorical questions, headlines) and reads
  `…, — X` as attribution to X; Pass 3 receives each claim's source and whether it is the target,
  so self-presentation and neutral reports of actions are `відсутнє`. State-body aliases in a
  foreign context (`Міноборони рф`, `МЗС КНР`) no longer admit Ukrainian registry entities. Stored
  posts are re-analyzed through a maintenance script; a newer completed run of a revision marks the
  previous one `superseded`, and analytics read only completed statuses.
- Inference v4 (migration 014) makes five model calls. A `candidates` call shows every alias match
  with its sentences and confirms or rejects it, so common-word aliases (`Голос`, `ЧЕСНО`) need no
  case rule; Pass 1 keeps the v3.6 prompt and a broken Pass 1 response is salvaged before repair.
  A `targets` call names, per claim, every actor the claim source evaluates, and the other pairs
  become `відсутнє` without Pass 3. The matcher inflects feminine adjectives and `-ість` nouns,
  Pass 2 no longer links a claim to neutral background entities, and Pass 3 keeps the v3.5.2 rule
  that an event involving a target is not the source's evaluation of it. On the measure-only test
  split negative F1 is 0.728 against 0.682 for v3.6. The worker image still runs v3.6 until it is
  rebuilt; stored posts are not re-analyzed without an explicit decision.
- `golden_v0/test_split.json` (v2) is a measure-only test split of 249 fresh, registry-matched
  production posts (the `test` partition, `golden_v0-666`..`golden_v0-914`, 81 negative and 109
  positive gold pairs) annotated after the prompt work; only aggregate metrics are reported on
  them. Prompt work iterates on the other 500 (`--split dev`).
- Inference v4.9 (unmerged, branch `v4.4-golden-v3`) is the recommended candidate: v4.4 prompts,
  the 812 specific registry aliases of migration 015, and an `affiliations` call that carries a
  negative stance toward a person the post presents as head, member or former employee of a
  monitored organization over to that organization. On dev, against the gold with affiliations
  and the alias supplement, negative P/R/F1 is 0.75/0.78/0.768 (v4.4 0.78/0.68/0.728). A direct
  post x entity prototype (`experiments/dspy/src/mamay_direct.py`) reached the same F1 band, so
  the remaining gap is the model, not the pipeline shape.
- `golden_v0` follows the positive-context stance convention (v2): a source that presents an
  entity in a positive context — successes, results, high trust, its own reports of success, a
  favourably framed routine action — is `positive` without explicit praise. All 1484 neutral
  stance records were re-reviewed and 427 became positive (`data/stance_relabel_log.jsonl`);
  positive pairs per split went from 22 to 109 on test. Experimental branches `v4.3` (Pass 2 once
  per monitored entity) and `v4.4` (Pass 3 and targets follow the v2 convention) reach dev
  negative F1 0.774 and positive F1 0.655 against 0.745 and 0.464 for v4 on main; neither is
  merged or deployed yet.
- `golden_v0` is an offline, DVC-tracked pilot for annotation-schema validation. The offline Mamay
  comparison generator reuses the worker's inference request boundary to pair each golden input,
  full reviewed annotation, and Mamay output for external review. Parsed outputs that fail local
  validation are retained with their validation category; it does not score or judge the outputs
  and does not make the AI worker a runtime dependency on DVC.
- `golden_v0` has 500 examples: the original 100 (`pilot100`) and 400 Claude-annotated posts
  (`extension400`, `golden_v0-266` to `golden_v0-665`) imported through the editor's import
  confirmation; `data/annotation_provenance.jsonl` records the annotator of every example. Benchmark reports keep extension examples out of `diagnostic45` and `all100` and report
  them as `extension400` plus a combined `all` section.
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
- `jev_vs_golden_v1` to `jev_vs_golden_v4` are DVC-tracked, classification-only runs of
  TypeSafe's Jev typed-decision model through OpenRouter, using reviewed `golden_v0` claims as
  input. Prompts were iterated on `old55` only. With prompt `v4` and no tuned thresholds, Jev matches
  Mamay v3.5.2 stance on Mamay's aligned `diagnostic45` pairs and exceeds it on rhetoric and
  claim-target attack detection; post-level attack detection remains slightly lower. The
  end-to-end `jev_hybrid_v3_6` run, where Jev classifies Mamay v3.6's own claims, ties Mamay v3.6 on
  stance, improves rhetoric labels, and lowers post-level attack recall; it does not by itself
  justify an external classification dependency.
  Production inference is unchanged and does not call external providers.
- `mamay_vs_golden_v3_6` is the DVC-tracked v3.6 run over the 100 reviewed examples. Against
  v3.5.2 it misses 8 instead of 20 attacked posts (4 false instead of 1): post-level attack F1
  0.849 → 0.922, negative-stance recall 0.68 → 0.87, positive-stance precision 0.61 → 0.73,
  claim coverage 0.59 → 0.62; negative-stance precision falls 0.97 → 0.92. Paired post-level
  bootstrap 95% intervals exclude zero for attack F1, negative recall and the negative-precision
  drop. A blind Claude Haiku comparison through subagents (not production, outside DVC) scored
  higher on attribution and rhetoric but extracted about 30% fewer claims.
- `luna_vs_golden_v3_7_pilot100` and `luna_low_vs_golden_v3_7_pilot100` are DVC-tracked runs of
  the committed v3.7 pipeline on OpenAI GPT-6 Luna through OpenRouter over the 100 reviewed
  examples, with OpenRouter reasoning effort `none` and `low` (low adds 4096 output tokens per
  pass, since reasoning counts against `max_tokens`). The runner's CLI has no reasoning option;
  it was injected by wrapping the client, and `run_metadata.model` still records the Mamay
  default. With `none`, 7 posts fail on JSON followed by stray text (strict schema is not
  enforced). With `low`, all 100 complete and the old55/diagnostic45 results match or exceed
  Mamay v3.7 on post-level attack F1 (0.966/0.862), negative-stance precision, rhetoric micro-F1
  (0.525/0.443) and claim coverage (0.69/0.70); attribution accuracy (0.80/0.82) stays below the
  Haiku pilot. Production inference is unchanged.
- `registry_post_coverage` is a DVC-tracked snapshot of the number of latest accessible posts
  matching each active registry entity under the production alias policy. Its summary records the
  live queue and a throughput-based ETA; it is an operational snapshot, not a model evaluation.

## Documentation

Product context for UI work is recorded in `../PRODUCT.md`; the incumbent visual system (tokens,
type, components, and rules) is recorded in `../DESIGN.md` with extensions in
`../.impeccable/design.json`.

The Kryvda investigation UI uses a light liquid-glass system: frosted glass tiles over a calm,
slowly animated ASCII field whose ripples echo attack spikes (hovering a daily bar sends one), a
floating capsule navigation, and SF Pro on Apple devices with self-hosted Inter elsewhere. The
overview is a bento: a dark glass hero with the negative count and daily chart, the period's main
target, summary tiles, the most frequent rhetoric technique, rankings, the target map with its
always-open list, movers and the rhetoric distribution. Edge refraction (an SVG displacement map
in `backdrop-filter`) renders on Chromium for pills and the dark and accent tiles; other engines
keep the frosted blur. Motion and refraction stop under `prefers-reduced-motion`, and glass turns
solid under `prefers-reduced-transparency`.
The overview leads with negative classifications, temporal activity, attacked-entity rankings,
channel comparisons, and auditable claims. Entity profiles add stance-over-time, epistemic-status,
and attribution distributions. Their URL-backed global filters distinguish publication channel from
claim attribution: a single `Джерело твердження` control offers all claims, channel position, or quoted
sources. Quoted sources can be refined to all quoted claims, named authors, or unnamed sources; the
inline author finder lists only named registry actors that occur in the current filtered Entity scope and
shows each actor's claim count. The stable registry identity remains the API `source_entity_id`; every
Entity aggregate and its evidence feed shares the same scope. Evidence separately labels publication
channel and statement author. Select controls use Ukrainian visible labels and responsive, wrapping menus;
Entity filters group primary controls separately from expandable additional analytical controls. Channel rows now open `/channels/{id}` profiles with activity,
stance, entity, rhetoric, epistemic, attribution, and recent-claim analysis. Post detail uses a
source/analysis split view and exposes evidence, target, stance, rhetoric, epistemic status, and
attribution for every extracted claim.

Analytical lists use server-side offset pagination (25 records by default). Entity and channel
rankings distinguish absolute negative volume from negative evaluative balance: the latter ranks the
Wilson lower bound (z = 1.96) of negative classifications among positive and negative evaluations.
Rows show positive and negative shares, their evaluative sample size, and separately report the
technical `відсутнє` classification, which never enters that denominator. Full analytical lists offer
negative volume, negative balance, positive volume, and total evaluative-volume ordering; the
dashboard exposes volume and balance as separate quick views. Registry aliases remain search-only
internal data and are never included in analytical responses. The shared 7, 30, and
90-day presets, all-time option, and custom inclusive calendar range are encoded in the URL and
preserved across top-level navigation. Entity and channel chart selections are also URL-backed and
filter their evidence or claims. Entity analytics excludes the technical `відсутнє` classification
from its evaluative totals. Rhetoric shares count assigned labels, while epistemic and attribution
shares count distinct claims; the interface labels these denominators explicitly.

Every chart section is a shareable card: a data-driven thesis headline and a dateline under it
(section, subject, period with year, active filters). The exported PNG alone adds a footer with the
«кривда.» wordmark, the source line and the partner credit; on screen these appear once, in the site
footer («Досліджуємо український інформаційний простір…» and «Спільний проєкт ЦПК, катедри СШІ
Львівської політехніки та платформи інференсу мовних моделей Lapathoniia»). Exports render the card
on solid white without glass effects. Headlines state a
finding only above sample guardrails (`apps/frontend/src/lib/theses.ts`) and otherwise describe the
graphic; the overview title names the period's main target under the same guardrail. A
`Зберегти зображення` control renders the card at 2x pixel ratio through `html-to-image` and opens a
preview dialog; the PNG is saved only after the analyst confirms. Controls marked
`data-export-ignore` and term underlines are excluded. Interactive charts carry a keyboard data
table that offers the same drill-down, and on phones the target map becomes a ranked quadrant list.
Channel profiles add their own target map of the entities that channel evaluated; its points open
entity profiles filtered to the channel.

The identity is the lowercase «кривда» wordmark closed by a round red full stop (`BrandLockup`),
which gathers into a glass bubble once the page scrolls; favicons and the app icon are a dark
rounded plate with a white Inter Bold «к» and the red dot (`apps/frontend/public/kryvda-mark.svg`,
`favicon.ico`, `apple-touch-icon.png`). When collection has stopped inside the chosen window, the
overview hero says since which day there are no new posts. Registry entities show a portrait or emblem
where Wikidata links a freely licensed Wikimedia Commons image to a confidently matched item (68 of
128: 55 portraits, 13 near-square emblems; wide text logos and ambiguous namesakes fall back to
initials). Files live in `apps/frontend/public/entity-photos/`, the manifest with author, licence
and source in `apps/frontend/src/lib/entity-photos.json`, and the site footer lists every
attribution. Entity and channel profiles flag sources whose last claim or post is more
than three days old. Failed requests show a retry action that keeps URL-backed filters. `/system`
is a non-exportable admin overview: a status pill, a 7/30/90-day window, a dark throughput hero
(finished runs per Kyiv day by outcome with the collected-post line on its own scale, typical run
time from the median), queue tiles, a model-pass quality table (attempts, repair share, invalid
share, median and 95th-percentile latency, completion tokens), the last 48 hours, per-channel
collection pulses with freshness, retry reasons, and model/pipeline usage. It reads
`/analysis/health`, `/channels/collection-health` and `/system/activity`. A header toggle switches
the animated background off on slower machines; the choice is remembered per browser. nginx
revalidates `index.html` on every visit and caches hashed assets for a year, so deploys reach
browsers immediately.

The overview opens with a metric strip whose counts carry a sparkline and the relative change
against the equally long previous period (fetched as a second request; unavailable for «Увесь
час»). Daily charts render bars, never interpolated areas, with a day/week toggle (weeks by default
beyond 120 days), spikes highlighted when a bin exceeds the period mean + 2σ and at least 5, and a
dashed mean line; clicking a bar narrows the page to that day or week. Stance-over-time stacks
negative and positive classifications with a trailing 7-day negative-share line (hidden below 5
evaluations). A target map plots entities by evaluative volume (log scale) against negative share,
split at the median volume and 50% into four named quadrants, and «Кого атакували більше, ніж
раніше» lists the largest growth in negative classifications against the previous period. Entity
and channel rankings are diverging bars: negative extends left and positive right from one shared
axis and scale, with the evaluative sample size per row. Negative is red (`--negative`) and positive
is blue (`--positive: #2d5d9f`) for colour-vision-deficiency safety.

The interface is Ukrainian-only. `apps/frontend/src/lib/glossary.ts` is the single source of UI
terms: each term has a visible `label`, an optional `definition` shown in a tooltip next to the
term (stance, rhetoric, epistemic and attribution labels, metrics, quadrants, pipeline states), and
a `draft` flag for translations awaiting editorial review. A regression test fails on Latin words
in rendered text or accessible names, allowing only «Telegram» and data such as channel names.

Every `daily` series from `/dashboard`, `/channels`, `/channels/{id}/analytics`, and
`/entities/{id}/analytics` buckets posts by `Europe/Kyiv` calendar day and returns one row per day
of the requested range, zero-filled where no analysis exists (an unbounded range spans the first
analysed day to today in Kyiv).

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
## Claims Explorer and analytical completeness

`/claims` is the primary investigation workspace for URL-backed claim filtering. Analytical aggregates include valid persisted records from `completed_with_partial_classification` and `completed_with_entity_fallback` runs; the Dashboard exposes completeness counts so degraded and unfinished coverage is visible. Operational AI queue details live on `/system`, not the main Dashboard. Entity-facing evaluative-claim totals are labelled as claims/classifications rather than mentions.

## Kubernetes deployment

`k8s/` adds the Mac mini Argo CD deployment, with amd64 GHCR builds, Sealed Secrets,
ordered database initialization/migrations, node-local persistent storage, and daily backups.
Compose remains supported. See `docs/deploy/mac-mini-argocd.md` for bootstrap requirements;
external integration credentials must be supplied before activating the Application.
