# Annotation guidelines v1

## Scope

Annotate only information observable in the selected Post Revision. Preserve the source text and
use it as the sole evidence for stance, claims, and rhetorical features. Registry resolution may
use verified aliases or annotator knowledge during review, but record its source and do not use
external knowledge to infer a claim, stance, or rhetorical feature.

## Entities

Annotate actors relevant to monitoring: people, organisations, state institutions, media outlets,
and political actors. Capture every textual mention with its exact half-open Unicode span. Assign
one entity type and a registry status: `candidate`, `monitored`, or `ignored`.

Do not create an entity for incidental non-monitoring people: minors, victims, witnesses,
unnamed commentators, anonymous sources, or generic roles without an identifiable monitoring
actor. They must not receive a canonical name or a registry candidate. An unnamed external voice
may still be recorded as `external_unnamed` attribution for a claim about an in-scope actor; do
not invent a source entity for it. Still annotate a claim, stance, or rhetorical feature that
targets a relevant actor even when its text also mentions one of these excluded people.

The import draft may propose a canonical name, but it cannot set a registry ID. During the reviewed
confirmation step, an exact canonical-name/entity-type match reuses its registry entry; otherwise
the verified proposal becomes a `candidate`. Leave canonical name empty when it is not reliable.

`primary` means that the post centrally concerns or materially evaluates the entity. Several
entities may be primary. Speakers cited only to frame another entity are normally `secondary`.

## Stance

Create a stance record for each observed perspective toward an annotated entity. The perspective
may be the channel's editorial voice, a named entity, an unnamed external source, or unknown.
Use `insufficient_context` when publication or quotation alone does not establish the channel's
own stance. Evidence must point to the supporting source span.

## Claims

Split independent propositions into atomic claims. Normalize each claim as a concise Ukrainian
declarative sentence without adding facts. Preserve negation, attribution, and uncertainty.
Record every participating entity, the evidence span, attribution, presentation form, and
epistemic status.

`presentation` describes how the post carries the claim: `editorial`, `direct_quote`, `reported`,
or `repost`. `epistemic_status` describes its force: `asserted`, `alleged`, `denied`,
`hypothetical`, or `questioned`.

## Rhetorical features

Rhetorical features are separate observable signals, not stance labels and not an attack label.
Use only the taxonomy in the schema. Each occurrence needs an evidence span, its perspective, and
a target entity or claim whenever the target is identifiable.

## Out of scope

Do not annotate narratives, waves, campaigns, coordination, an attack score, or a post-level
information-attack label. An Information Attack is a future aggregate analytic result based on
similar negative narrative across several channels in a close time period.
