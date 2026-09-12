# Offline experiments

`mamay_golden_v0.py` creates evidence for a human or external ChatGPT review; it does not score,
rank, or judge Mamay. Each row pairs the exact post text with the complete reviewed `golden_v0`
annotations and Mamay's runtime extraction. Parsed outputs that fail local grounding validation are
preserved as `status: "invalid"` with a validation category for external review; request or JSON
failures use a sanitized failure record.

Validate the source data first:

```bash
uv run python experiments/datasets/golden_v0/src/golden_v0_validation.py
```

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

## Inference v3.1 hardening comparison

The same `mamay_golden_v2.py` runner now defaults to a separate
`mamay_vs_golden_v3_1` directory and the unchanged 55-row `golden_v0` input. Each row adds
sanitized primary/repair payloads and final per-pass diagnostics. `summary.json` reports status,
primary-versus-repair validity and categorized failure counts against the preserved v3 baseline.

```bash
uv run python experiments/dspy/src/mamay_golden_v2.py
uv run python experiments/dspy/src/mamay_golden_v2.py --validate-only
uv run dvc add experiments/dspy/data/mamay_vs_golden_v3_1
uv run dvc status
```
