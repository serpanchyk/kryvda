# golden_v0

`golden_v0` is an approximately 100-example manually annotated pilot for Telegram post semantic
extraction. Each example refers to one immutable Post Revision and retains the exact text used for
annotation.

The DVC-tracked `data/` directory contains two JSONL files:

- `selection_manifest.jsonl` records why an immutable Post Revision was selected.
- `annotations.jsonl` contains the completed annotation records defined by
  `annotation_schema_v1.json`.

Start with a deliberately diverse sample from all available monitored channels. Include different
entities, stance values, quotations, indirect mentions, reposts, modality, and rhetorical
features. Include examples with no relevant monitoring actor or claim: an empty annotation result
is valid evidence that the extraction pipeline found nothing in scope, rather than a special
false-positive label.

Run `uv run python experiments/datasets/golden_v0/src/golden_v0_validation.py` after every
annotation change. The command validates the JSON Schema, span boundaries, surface forms, and
cross-record references.
