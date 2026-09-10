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
