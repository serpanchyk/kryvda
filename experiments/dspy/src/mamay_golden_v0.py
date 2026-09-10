"""Generate resumable Mamay outputs paired with reviewed golden_v0 annotations."""

import argparse
import asyncio
import json
import logging
import os
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from monitoring_common.contracts import ExtractionValidationError, validate_extraction
from monitoring_common.logging import setup_logging
from telegram_monitor_ai_worker.client import LiteLlmExtractionClient
from telegram_monitor_ai_worker.models import ModelOutputError
from telegram_monitor_ai_worker.prompt import PROMPT_VERSION

DEFAULT_ANNOTATIONS = Path("experiments/datasets/golden_v0/data/annotations.jsonl")
DEFAULT_OUTPUT = Path("experiments/dspy/data/mamay_vs_golden_v0/comparisons.jsonl")
DEFAULT_MODEL = "MamayLM-Gemma-3-27B-IT"
DEFAULT_BASE_URL = "http://litellm:4000"
DEFAULT_TIMEOUT_SECONDS = 120
COMPARISON_SCHEMA_VERSION = "mamay_golden_comparison_v1"


class ExtractionClient(Protocol):
    """The production extraction boundary used by this offline experiment."""

    async def extract(self, post_text: str) -> dict[str, Any]:
        """Return one decoded model payload."""


def load_annotations(path: Path) -> list[dict[str, Any]]:
    """Load golden records and reject duplicate identifiers before calling the model."""
    records: list[dict[str, Any]] = []
    example_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"annotation line {line_number} must be an object")
        example_id = record.get("example_id")
        if not isinstance(example_id, str):
            raise ValueError(f"annotation line {line_number} has no string example_id")
        if example_id in example_ids:
            raise ValueError(f"duplicate golden example_id: {example_id}")
        source = record.get("source")
        annotations = record.get("annotations")
        if not isinstance(source, dict) or not isinstance(source.get("text"), str):
            raise ValueError(f"annotation {example_id} has no source text")
        if not isinstance(annotations, dict):
            raise ValueError(f"annotation {example_id} has no annotations object")
        example_ids.add(example_id)
        records.append(cast(dict[str, Any], record))
    return records


def completed_example_ids(path: Path) -> set[str]:
    """Return already persisted rows so interrupted runs can resume safely."""
    if not path.exists():
        return set()
    completed: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("input"), dict):
            raise ValueError(f"comparison line {line_number} has no input object")
        example_id = row["input"].get("example_id")
        if not isinstance(example_id, str):
            raise ValueError(f"comparison line {line_number} has no string example_id")
        if example_id in completed:
            raise ValueError(f"duplicate comparison example_id: {example_id}")
        completed.add(example_id)
    return completed


def build_row(
    annotation: Mapping[str, Any],
    mamay_output: Mapping[str, Any] | None,
    failure_kind: str | None,
    model: str,
    run_timestamp: str,
) -> dict[str, Any]:
    """Build one self-contained comparison row without judging either output."""
    source = cast(Mapping[str, Any], annotation["source"])
    result: dict[str, Any]
    if mamay_output is not None:
        result = {"status": "valid", "output": dict(mamay_output)}
    else:
        result = {
            "status": "failed",
            "failure": {
                "kind": failure_kind,
                "message": "Model output was unavailable or failed local contract validation.",
            },
        }
    return {
        "comparison_schema_version": COMPARISON_SCHEMA_VERSION,
        "input": {
            "example_id": annotation["example_id"],
            "post_revision_id": source["post_revision_id"],
            "post_text": source["text"],
        },
        "golden_output": annotation["annotations"],
        "mamay_output": result,
        "run_metadata": {
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "schema_version": "extraction_schema_v1",
            "temperature": 0,
            "run_timestamp": run_timestamp,
        },
    }


async def generate_comparisons(
    annotations: Sequence[Mapping[str, Any]],
    output_path: Path,
    client: ExtractionClient,
    model: str,
    logger: logging.Logger,
) -> tuple[int, int]:
    """Append missing comparison rows and return counts for written and failed examples."""
    completed = completed_example_ids(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    failures = 0
    with output_path.open("a", encoding="utf-8") as output_file:
        for annotation in annotations:
            example_id = cast(str, annotation["example_id"])
            if example_id in completed:
                continue
            source = cast(Mapping[str, Any], annotation["source"])
            post_text = cast(str, source["text"])
            run_timestamp = datetime.now(UTC).isoformat()
            try:
                payload = await client.extract(post_text)
                validate_extraction(payload, post_text)
                row = build_row(annotation, payload, None, model, run_timestamp)
            except Exception as error:
                failure_kind = classify_failure(error)
                row = build_row(annotation, None, failure_kind, model, run_timestamp)
                failures += 1
                logger.warning(
                    "comparison model output failed",
                    extra={"example_id": example_id, "failure_kind": failure_kind},
                )
            output_file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            output_file.flush()
            written += 1
            logger.info("comparison row written", extra={"example_id": example_id})
    return written, failures


def classify_failure(error: Exception) -> str:
    """Classify failures without persisting provider messages that may expose secrets."""
    if isinstance(error, ModelOutputError):
        return "invalid_model_response"
    if isinstance(error, ExtractionValidationError):
        return "invalid_extraction_contract"
    return "model_request_failed"


def parse_args(arguments: Iterable[str] | None = None) -> argparse.Namespace:
    """Parse the small CLI surface for a reproducible experiment run."""
    parser = argparse.ArgumentParser(description="Generate Mamay and golden_v0 comparison JSONL")
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=os.environ.get("LITELLM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args(arguments)


async def run(arguments: Iterable[str] | None = None) -> None:
    """Run the resumable comparison generator using the configured internal LiteLLM proxy."""
    args = parse_args(arguments)
    api_key = os.environ.get("LITELLM_API_KEY")
    if not api_key:
        raise RuntimeError("LITELLM_API_KEY must be configured for the Mamay comparison run")
    annotations = load_annotations(args.annotations)
    logger = setup_logging("telegram-monitor-mamay-golden-experiment")
    client = LiteLlmExtractionClient(args.base_url, api_key, args.model, args.timeout_seconds)
    try:
        written, failures = await generate_comparisons(
            annotations, args.output, client, args.model, logger
        )
    finally:
        await client.close()
    logger.info(
        "comparison run complete",
        extra={"written": written, "failures": failures, "total_examples": len(annotations)},
    )


def main() -> None:
    """Run the generator as a command-line program."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
