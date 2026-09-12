# Inference v3

Production analysis is target monitoring. A Post Revision is eligible only when a Unicode-aware,
case-insensitive literal match finds an approved alias of a monitored registry entity. Matching
requires letter/digit boundaries and performs no fuzzy or morphological search.

The AI worker makes exactly three semantic model calls:

1. `entities` groups exact textual references to relevant identifiable actors.
2. `claims` extracts atomic claims involving at least one monitored entity, with attribution,
   Ukrainian epistemic status, and one exact evidence string.
3. `classification` classifies every monitored claim-target pair for Ukrainian stance and up to
   two attack-rhetoric categories.

Between calls, backend code validates grounding, resolves approved aliases, assigns `e*` and `c*`
IDs, records candidates, and derives deterministic evidence offsets. Pass 2 receives the whole
post. Pass 3 receives the normalized claim, exact evidence, and the evidence sentences with one
neighboring sentence on each side.

Schemas live in `monitoring_common/contracts/schemas/inference_v3_*`. Prompts are Ukrainian and
technical JSON keys remain English. IDs, canonical resolution, offsets, candidates, persistence,
and retry bookkeeping are deterministic backend responsibilities.

Every primary response is persisted raw before dependent work proceeds. JSON parse, schema,
grounding, and reference failures receive one repair request containing the original output,
categorized validation errors, and expected schema. A second failure is terminal. Generation and
provider failures retain separate categories. Successful prior passes are reused after transient
job retries.

Final results are stored relationally as post-local entities, atomic claims, claim/entity links,
and claim-target classifications. `analysis_runs.final_payload` keeps an inspectable immutable v3
document. Aggregation and product analytics are intentionally deferred.

The previous `extraction_schema_v1` remains packaged only so historical DVC experiments can be
reproduced; it is no longer a production runtime contract.
