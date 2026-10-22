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

## Measure-only test split

`test_split.json` (v2) lists the 249 examples of the `test` partition. Report aggregate metrics
on them, but never read, print or analyse their individual outputs or errors while designing
prompts or pipelines; inspect errors only on the other 500 examples (`dev`). The first attempt
(v1, 100 never-inspected `extension400` posts) held only 11 negative pairs, because the inspected
examples were exactly the ones with stance, so v2 uses fresh posts instead: the same production
selection as `extension400` (registry-matched posts only), excluding every earlier golden_v0 post
and the 200 posts reviewed for inference v3.6, annotated by Claude subagents with the extension
brief. Gold holds 81 negative and 22 positive post x registry-entity pairs; 187 posts carry no
stance and measure false positives. When the split has been used to choose between many
variants, add fresh test posts instead of reusing it.

```bash
uv run python experiments/datasets/golden_v0/src/golden_v0_extension.py --target 150 \
  --work experiments/datasets/golden_v0/extension/test_work2 --seed 20261025 --core-share 1.0 \
  --no-calibration --exclude-review-sample experiments/dspy/data/analysis_sample_200.json
uv run python experiments/datasets/golden_v0/src/golden_v0_extension_import.py import b01 b02 \
  --work experiments/datasets/golden_v0/extension/test_work2 --partition test
```

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

Import merges variant spellings of one actor and fixes entity types for actors the local
registry lists twice (`CANONICAL_VARIANTS` and `TYPE_OVERRIDES` in
`golden_v0_extension_import.py`). Annotators omit named actors that take part in no claim, so
entity-level extraction recall is less complete in `extension400` than in `pilot100`.

Every extension claim target has exactly one stance record overlapping the claim evidence, so
the canonical adapter leaves no stance unresolved.

## Positive-context convention (v2)

Since 2026-10-21 `positive` means that the source presents the entity in a positive context,
even without explicit praise: its successes and results, high trust or ratings, its own
announcement of its successes, or a routine action the post frames favourably. Only a flat,
informational mention stays `neutral`. The extension and test annotations originally put all of
these in `neutral`, so every neutral stance record of all partitions was re-reviewed by Claude
subagents (blind to model outputs) and the changes appended to `data/stance_relabel_log.jsonl`.
On 2026-10-22 the owner adjudicated 40 dev disagreements between Mamay v4.4 and the gold
(`extension/adjudication_v4_4`): the gold was right on 17 of 21 decided negative pairs but on
only 8 of 15 positive ones, because self-presentation and received support had stayed neutral.
A second blind pass with that calibration (`extension/relabel_v3_work`, convention
`positive_context_v3_owner_calibrated`) turned 155 more neutral records positive.

```bash
uv run python experiments/datasets/golden_v0/src/golden_v0_stance_relabel.py export
# Reviewers write batches/rNN/out.json next to every items.json; the editor must be stopped.
uv run python experiments/datasets/golden_v0/src/golden_v0_stance_relabel.py apply
uv run python experiments/datasets/golden_v0/src/golden_v0_validation.py
```

## Person-to-organization criticism (2026-10-23)

Criticism of a person is criticism of an organization when the post itself presents the person
as its head, member, employee or former employee («голова ЦПК Шабунін», «ексдетектив НАБУ»).
`data/affiliations.jsonl` lists those links for every post with a negatively evaluated person
and a monitored registry organization in its text (178 posts, 166 links), annotated by Claude
subagents blind to model outputs; the post x entity stance report adds a negative stance for
each linked organization. The gold then holds 341 instead of 290 negative dev pairs.

```bash
uv run python experiments/datasets/golden_v0/src/golden_v0_affiliations.py export
# Reviewers write batches/aNN/out.json next to every items.json.
uv run python experiments/datasets/golden_v0/src/golden_v0_affiliations.py collect
```
