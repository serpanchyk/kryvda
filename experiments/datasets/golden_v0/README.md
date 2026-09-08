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
features. Reserve roughly 10--15% for keyword matches with no relevant monitoring entity or claim.
Those examples must have empty `annotations.entities`, `annotations.stances`,
`annotations.claims`, and `annotations.rhetorical_features`.

Run `uv run python experiments/datasets/golden_v0/src/golden_v0_validation.py` after every
annotation change. The command validates the JSON Schema, span boundaries, surface forms, and
cross-record references.
