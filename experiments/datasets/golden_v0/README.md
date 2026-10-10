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

## Extension to 500 examples

`extension400` adds Claude-annotated posts to the same dataset. `data/annotation_provenance.jsonl`
records the annotator and partition of every example (`pilot100` for the original ChatGPT-drafted,
partly reviewed records). The selection, annotator brief, references, batches and raw outputs live
in the DVC-tracked `extension/work` directory; the brief itself is `extension/ANNOTATOR_BRIEF.md`.

```bash
# Read-only selection from PostgreSQL into extension/work (400 posts in batches of 10).
uv run python experiments/datasets/golden_v0/src/golden_v0_extension.py --target 400
# Check one annotated batch; annotators fix every ERROR.
uv run python experiments/datasets/golden_v0/src/golden_v0_anchor.py check-dir \
  experiments/datasets/golden_v0/extension/work/batches/b01
# Agreement of the blind calibration batch with the original annotations.
uv run python experiments/datasets/golden_v0/src/golden_v0_extension_import.py calibration
# Import validated batches through the editor's complete-import (editor must be stopped).
uv run python experiments/datasets/golden_v0/src/golden_v0_extension_import.py import b01 b02
uv run python experiments/datasets/golden_v0/src/golden_v0_validation.py
uv run dvc add experiments/datasets/golden_v0/data experiments/datasets/golden_v0/extension/work
```

Extension conventions differ from the original pilot in two documented ways: non-evaluative news
and self-presentation receive `neutral` rather than `positive` stance, and every claim target has
exactly one stance record overlapping the claim evidence, so the canonical adapter leaves no
stance unresolved.
