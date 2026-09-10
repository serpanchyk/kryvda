# Post-Analysis Extraction Contract

`extraction_schema_v1` is the shared contract for a model's candidate extraction from one Post
Revision. The source text and durable post metadata stay outside the response. The response holds
only entities, attributed stances, atomic claims, and rhetorical features grounded in exact
half-open Unicode evidence spans.

The versioned JSON Schema is packaged at
`monitoring_common/contracts/schemas/post_analysis_extraction_schema_v1.json`. Its field
descriptions are prompt-ready. `monitoring_common.contracts.validate_extraction` validates JSON
structure, local entity/claim references, span bounds, exact entity surface forms, and speaker
references against the supplied post text.

Canonical names, registry IDs, registry status, and resolution source are intentionally absent.
They require registry lookup, verified aliases, or human review and must be applied after
candidate extraction. Response-local `e*` and `c*` IDs are links within a single model response;
they are not durable database identifiers.

The prompt must require JSON only, source-text-only reasoning, empty arrays for absent evidence,
and `null` for `source_entity_id` unless `source_kind` is `named_entity`. The runtime validator
rejects unsupported fields and evidence that does not match the post text.
