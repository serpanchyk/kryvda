# Offline experiments

`mamay_golden_v0.py` creates evidence for a human or external ChatGPT review; it does not score,
rank, or judge Mamay. Each row pairs the exact post text with the complete reviewed `golden_v0`
annotations and Mamay's runtime extraction. Parsed outputs that fail local grounding validation are
preserved as `status: "invalid"` with a validation category for external review; request or JSON
failures use a sanitized failure record.

## Registry post coverage

`registry_post_coverage.py` produces a DVC-tracked snapshot of every active registry entity's
coverage among the latest accessible post revisions. It uses the production alias matcher, so a
post is counted once for each entity matched by one or more approved aliases. Its `summary.json`
also records the current analysis queue and a throughput-based ETA.

Run it in an ephemeral worker container, then validate and version the generated directory:

```bash
docker compose run --rm --no-deps -w /workspace -v "$PWD:/workspace" \
  -e PYTHONPATH=/workspace/apps/ai-worker/src:/workspace/packages/monitoring-common/src \
  ai-worker python /workspace/experiments/dspy/src/registry_post_coverage.py
uv run python experiments/dspy/src/registry_post_coverage.py --validate-only
uv run dvc add experiments/dspy/data/registry_post_coverage
uv run dvc status
```

The CSV and JSON contents are DVC-managed and must not be committed directly. No DVC remote is
currently configured.

Validate the source data first:

```bash
uv run python experiments/datasets/golden_v0/src/golden_v0_validation.py
```

## Canonical golden schema

Semantic evaluation consumes a single canonical representation. Immutable `golden_v0` records use
the deterministic legacy adapter. The v3.5.2 100-example report labels its tuned partitions
`old55`, `diagnostic45`, and `all100`; `diagnostic45` is not held-out. Inspect the migration
without changing its source data:

```bash
uv run python experiments/dspy/src/inspect_golden_mapping.py
```

To write a separately inspectable generated view, pass an output ending in
`.generated.jsonl`; never write it into the source dataset or DVC-add it as an annotation source.
The command reports mapped claims, generated claim-target classifications, unmapped legacy
rhetoric, ambiguous rhetoric-to-claim mappings, unresolved stances, and unresolved epistemics.
Native v1 evidence must
be an exact substring of `source.text`; classifications are the only stance/rhetoric objects and
must have empty rhetoric unless stance is `негативне`.

With the normal Compose stack running, execute the generator in an ephemeral AI-worker container.
The bind mount makes the input and DVC-managed output available while the container reaches the
internal-only LiteLLM service. It receives the existing `LITELLM_API_KEY` from Compose; do not put
the key in a command or output file.

```bash
docker compose run --rm --no-deps -w /workspace -v "$PWD:/workspace" \
  -e PYTHONPATH=/workspace/apps/ai-worker/src:/workspace/packages/monitoring-common/src ai-worker \
  python /workspace/experiments/dspy/src/mamay_golden_v0.py
```

The default output is `experiments/dspy/data/mamay_vs_golden_v0/comparisons.jsonl`. The command is
resumable: it preserves rows already written by `example_id`, including failure rows, and requests
only missing examples. To start a distinct run, pass a different `--output` path rather than
overwriting an existing DVC-managed dataset.

After the run, inspect the JSONL with the tool that will perform the review, then version it:

```bash
uv run dvc add experiments/dspy/data/mamay_vs_golden_v0
uv run dvc status
```

Commit the generated `.dvc` metadata, any DVC ignore-file update, source code, tests, and docs;
never commit the JSONL contents. No DVC remote is currently configured.

## Reduced Mamay v2 comparison

`mamay_golden_v1.py` is an experiment-only redesign of the Mamay-facing contract. It does not
change the production worker or `extraction_schema_v1`. The v2 schema replaces numeric spans with
exact text anchors, treats an entity as one distinct actor, retains literal source phrases where
available, and nests rhetoric within claims. It deliberately remains a one-pass full-post run.

Each row preserves the raw `golden_v0` annotation and adds `golden_v2_projection`, a deterministic
comparison projection without registry fields, spans, or rhetorical graph links. The projection
uses the first reviewed evidence span as its single evidence text. Since `golden_v0` does not
store literal phrases for unnamed sources, those projected source surfaces are `null`.

Run it through the same ephemeral worker container:

```bash
docker compose run --rm --no-deps -w /workspace -v "$PWD:/workspace" \
  -e PYTHONPATH=/workspace/apps/ai-worker/src:/workspace/packages/monitoring-common/src \
  ai-worker python /workspace/experiments/dspy/src/mamay_golden_v1.py
```

The output is `experiments/dspy/data/mamay_vs_golden_v1/comparisons.jsonl`. Validate its 55-row
coverage, then version the directory with `uv run dvc add experiments/dspy/data/mamay_vs_golden_v1`
and run `dvc status`.

## Inference v3 comparison

`mamay_golden_v2.py` runs the production target pre-filter and all three inference-v3 passes. Each
row retains the original reviewed annotation, character length, matched monitored entities, every
raw primary/repair response with validation details, backend resolution, and the final v3 output.
Posts without a supplied registry alias are recorded as `filtered_out` without model calls.

Run it through the AI-worker container while LiteLLM is healthy:

```bash
docker compose run --rm --no-deps -w /workspace -v "$PWD:/workspace" \
  -e PYTHONPATH=/workspace/apps/ai-worker/src:/workspace/packages/monitoring-common/src \
  ai-worker python /workspace/experiments/dspy/src/mamay_golden_v2.py
```

Validate and version the result without committing its JSONL contents:

```bash
uv run python experiments/dspy/src/mamay_golden_v2.py --validate-only
uv run dvc add experiments/dspy/data/mamay_vs_golden_v2
uv run dvc status
```

## Inference v3.5 semantic comparison

The same `mamay_golden_v2.py` runner now defaults to a separate
`mamay_vs_golden_v3_5` directory and the unchanged 55-row `golden_v0` input. Each row adds
sanitized primary/repair payloads, item-level sanitizer actions, and final per-pass diagnostics.
`summary.json` reports status, primary-versus-repair validity, categorized failures, and recovery
counts against the preserved v3.4 benchmark.

```bash
uv run python experiments/dspy/src/mamay_golden_v2.py
uv run python experiments/dspy/src/mamay_golden_v2.py --validate-only
uv run dvc add experiments/dspy/data/mamay_vs_golden_v3_5
uv run dvc status
```
