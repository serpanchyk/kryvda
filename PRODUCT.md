# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Analysts of ЦПК are the primary users. They investigate how a fixed, agreed pool of Telegram
channels portrays the actors in ЦПК's monitored-entity registry: who is attacked, by which
channels, with which rhetoric, how intensely over time, and on what textual evidence. Their job
ends in findings they can defend and publish.

A secondary, indirect audience is the public: chart cards exported from the interface are used
primarily in ЦПК's public posts, so an exported card is read by people who never saw the app.

## Product Purpose

Кривда continuously collects posts from the agreed channel pool, keeps every raw post revision,
filters posts against the human-maintained registry, and runs AI analysis that extracts atomic
claims and classifies each claim's stance and attack rhetoric toward each monitored entity. The
interface turns these classifications into investigation views: an overview, entity and channel
profiles, a claims explorer, source-post evidence, and system/pipeline health.

Success means an analyst can move from an aggregate pattern ("this entity is attacked more than
before") to the exact claims and source posts behind it, and publish a chart that is accurate and
self-explanatory outside the app.

## Positioning

The unit of analysis is an attributed, atomic claim about a specific registry entity, not a post
and not a keyword hit. Stance is attribution-aware: a channel reporting someone else's attack, an
adverse event, or a poll is not counted as the channel's own negative stance. An Information
Attack is only ever an aggregate finding across channels and time, never a label on one post.
Every number in the interface traces back to auditable claims and source posts.

## Operating Context

- Analysts work in the browser against a department-hosted deployment; only the frontend port is
  public and registry/candidate administration is not exposed in the UI.
- Investigation state (date range, filters, chart selections, pagination) lives in the URL, so
  views are shareable and reproducible.
- Date ranges: 7/30/90-day presets, all time, or a custom inclusive range; daily series are
  bucketed by `Europe/Kyiv` calendar day.
- Exported chart cards (PNG, 2x) carry their own thesis headline, period, source line, and the
  Кривда signature, and are posted publicly.

## Capabilities and Constraints

- Channel pool is fixed and agreed with ЦПК; the registry of monitored entities is curated by
  humans. Registry mutations stay outside the investigation UI.
- Vocabulary is defined in `docs/CONTEXT.md` and surfaced through
  `apps/frontend/src/lib/glossary.ts`, the single source of visible terms and their definitions.
  Terms marked `draft` await editorial review.
- Statistical honesty is part of the product: negative balance ranks by the Wilson lower bound,
  rows show evaluative sample size, the technical «без оцінки» classification never enters share
  denominators, denominators are labelled, daily charts use bars rather than interpolated areas,
  and comparisons against the previous period are unavailable for «Увесь час».
- Analytical completeness is visible: partial and fallback analysis runs are counted and disclosed.
- Later, additive capabilities (not built): narrative clustering, claim similarity, campaign
  detection, unusual mention waves, notifications.

## Brand Commitments

- The product name is Кривда.
- The interface is Ukrainian-only. All visible text and accessible names use Ukrainian terms from
  the glossary; Latin script is allowed only for «Telegram» and data such as channel names. A
  regression test enforces this.
- The current wordmark, palette, and typefaces are the incumbent implementation, not locked brand
  assets.

## Evidence on Hand

- Real collected data from the five seeded public channels (INSIDER UA, Україна Сейчас, Реальна
  війна, Україна Online, Times of Ukraine) and a 128-entry monitored registry.
- DVC-tracked golden and comparison datasets used for annotation and model validation; these are
  operational and contract-health measurements, not published accuracy scores.
- No testimonials, case studies, press coverage, or published accuracy benchmarks exist; do not
  fabricate them.

## Product Principles

1. Evidence first: every aggregate must lead to the claims and source posts that produce it.
2. Honest numbers: show sample sizes and denominators, avoid statistics that overstate small
   samples, and never imply precision the data does not have.
3. Attribution matters: distinguish publication channel from the author of a claim, and a
   channel's own stance from what it reports.
4. A chart must stand alone: anything exported must be understandable to the public without the app.
5. Ukrainian, precise, and defined: every analytical term is Ukrainian and has an explanation.

## Accessibility & Inclusion

Positive versus negative evaluation is currently encoded in a colour-vision-deficiency-safe pair
(blue versus red) with text labels; keep evaluative encodings distinguishable without relying on
red/green. Term definitions are available as tooltips on every analytical label.
