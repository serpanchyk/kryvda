# Inference v3.5

Production analysis is target monitoring. A Post Revision is eligible only when a Unicode-aware,
case-insensitive match finds an approved alias of a monitored registry entity. Exact matches use
letter/digit boundaries. A conservative deterministic Ukrainian/Russian nominal-inflection
matcher also recognizes grammatical forms token by token. A bare inflected surname from a person
alias is accepted only when it uniquely identifies one monitored registry entity; it does not
perform fuzzy matching.

The AI worker makes exactly three semantic model calls:

1. `entities` groups exact textual references to relevant identifiable actors.
2. `claims` extracts atomic claims involving at least one monitored entity, with attribution,
   Ukrainian epistemic status, and one exact evidence string. `presentation` is deliberately not
   stored or inferred.
3. `classification` classifies every monitored claim-target pair for Ukrainian stance and up to
   two attack-rhetoric categories.

Between calls, backend code validates grounding, resolves approved aliases including inflected
forms, assigns `e*` and `c*` IDs, records candidates, and derives deterministic evidence offsets.
Before Pass 1 validation it removes repeated strings and ungrounded strings, retaining each entity
group that still has at least one exact mention. Backend-created entities preserve every exact
surface form that caused the monitored prefilter match; Pass 1 entities merge into this set. If
Pass 1 remains invalid after repair, the pipeline continues with these prefilter entities only.
A mention repeated inside one group is harmless;
the same grounded mention in separate groups remains a reference failure. Mixed Pass 1 groups are
partitioned by uniquely resolvable mention, leaving ambiguous text as a post-local candidate. Pass
2 receives the whole post. Its deterministic sanitizer drops only invalid or non-monitored claims,
deduplicates retained claims, and realigns uniquely recoverable quote/dash/whitespace evidence to
the exact source substring. `claims: []` is valid. Pass 3 receives the normalized claim, exact
evidence, and the evidence sentences with one neighboring sentence on each side.

Schemas live in `monitoring_common/contracts/schemas/inference_v3_*`. Prompts are Ukrainian and
technical JSON keys remain English. IDs, canonical resolution, offsets, candidates, persistence,
and retry bookkeeping are deterministic backend responsibilities. Pass 3 splits stable expected
pairs into bounded requests (default five). After a whole-document parse failure it salvages only
complete classification objects, retries still-missing pairs in bounded batches, then retries each
remaining pair individually. A non-negative stance with returned rhetoric is sanitized to an empty
rhetoric list without changing the stance, so that invariant violation does not cause pair retry.
Permanently absent pairs produce partial completion without losing
successful classifications; diagnostics retain batch raw/parsed output, salvaged rows and errors.

Every primary response is persisted raw before dependent work proceeds. The flow is raw output,
deterministic sanitation, validation, and at most one repair followed by the same sanitation and
validation. Per-pass diagnostics retain both raw outputs, both sanitized payloads, categorized
validation errors, item-level sanitization actions, the final validation status and the final parsed payload. JSON parse, schema,
grounding, and reference failures remain distinct. A second failure is terminal. Generation and
provider failures retain separate categories. Successful prior passes are reused after transient
job retries.

Mamay calls use strict guided JSON and an explicit 4,096-token completion budget. The Pass 2
schema emits `source_entity_id` before `source_kind`, then `epistemic_status`: controlled probes
showed that the previous property orders let the model emit EOS before required fields, leaving
whitespace even when the token budget was raised.

Final results are stored relationally as post-local entities, atomic claims, claim/entity links,
and claim-target classifications. `analysis_runs.final_payload` keeps an inspectable immutable
v3.5 document, including completion/degradation status. The v3.5 prompt restricts
`external_unnamed` to explicit unnamed-source attribution, improves recall for explicitly
uncertain claims, and narrows corruption/personal-gain and hypocrisy/double-standard rhetoric.
Aggregation and product analytics are
intentionally deferred.

The previous `extraction_schema_v1` remains packaged only so historical DVC experiments can be
reproduced; it is no longer a production runtime contract.
