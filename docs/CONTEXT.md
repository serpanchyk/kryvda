# Ubiquitous Language

## Channel

An agreed Telegram publication source that the monitor is permitted to collect.

## Raw Post

The source record captured from a Channel before interpretation or analysis.

## Post Revision

An immutable observed version of a Raw Post's content.

## Backfill

Collection of a Channel's historical Raw Posts before ongoing monitoring.

## Collection Cursor

The durable position from which a Channel's collection safely resumes.

## Semantic Annotation

**Golden Dataset**:
A manually reviewed, versioned set of Post Revisions used to validate annotation and model output.
_Avoid_: Ground truth, final benchmark

**Entity Mention**:
The exact textual occurrence of a monitoring-relevant actor in a Post Revision.
_Avoid_: Generic NER result

**Canonical Entity**:
A registry identity that unifies Entity Mentions referring to the same actor.
_Avoid_: Surface form, guessed identity

**Claim**:
An atomic proposition expressed, reported, quoted, denied, hypothesized, or questioned in a Post
Revision.
_Avoid_: Narrative, information wave

**Stance**:
An attributed evaluative position toward an Entity Mention, supported by text in a Post Revision.
_Avoid_: Information attack

**Rhetorical Feature**:
An observable text-grounded device, such as ridicule or an accusation, separately annotated from
Stance.
_Avoid_: Attack flag

**Information Attack**:
An aggregate analytic finding about a similar negative narrative across multiple Channels in a
close time period; never a property of one Post Revision.
_Avoid_: Post-level label

**Analysis Job**:
A leased request to produce one candidate semantic extraction for a specific Post Revision.
_Avoid_: Analysis result, annotation

**Candidate Extraction Result**:
An immutable, validated model response under the extraction contract for one Post Revision; it is
not canonical resolution or a Golden Dataset annotation.
_Avoid_: Final annotation, registry decision
