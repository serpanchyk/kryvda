"""Generate auditable three-pass inference-v3 comparisons against golden_v0."""

import argparse
import asyncio
import json
import logging
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path
from typing import Any, Protocol, cast

from monitoring_common.contracts import (
    InferenceValidationError,
    PassName,
    ValidationIssue,
    parse_json_object,
    sanitize_pass_payload,
    validate_pass,
    validation_errors,
)
from monitoring_common.logging import setup_logging
from telegram_monitor_ai_worker.client import LiteLlmInferenceClient
from telegram_monitor_ai_worker.models import ModelOutputError, ModelResponse
from telegram_monitor_ai_worker.pipeline import (
    assign_claim_ids,
    classification_items,
    final_payload,
    matched_monitored_entity_ids,
    resolve_entity_groups,
)

DEFAULT_ANNOTATIONS = Path("experiments/datasets/golden_v0/data/annotations.jsonl")
DEFAULT_OUTPUT = Path("experiments/dspy/data/mamay_vs_golden_v3_1/comparisons.jsonl")
DEFAULT_BASELINE = Path("experiments/dspy/data/mamay_vs_golden_v2/comparisons.jsonl")
DEFAULT_SEED = Path("infra/postgres/init/003_registry_seed.sql")
DEFAULT_MODEL = "MamayLM-Gemma-3-27B-IT"
DEFAULT_BASE_URL = "http://litellm:4000"
COMPARISON_SCHEMA_VERSION = "mamay_golden_comparison_v3_1"


class InferenceClient(Protocol):
    """Primary and repair model calls used by the comparison runner."""

    async def infer(self, pass_name: PassName, request: dict[str, Any]) -> ModelResponse:
        """Return one primary pass generation."""

    async def repair(
        self, pass_name: PassName, original_raw: str, errors: list[dict[str, str]]
    ) -> ModelResponse:
        """Return one contract repair generation."""


def load_annotations(path: Path) -> list[dict[str, Any]]:
    """Load golden annotations with unique example IDs."""
    records: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        identifier = record.get("example_id") if isinstance(record, dict) else None
        if not isinstance(identifier, str):
            raise ValueError(f"annotation line {line_number} has no example_id")
        if identifier in identifiers:
            raise ValueError(f"duplicate example_id: {identifier}")
        identifiers.add(identifier)
        records.append(cast(dict[str, Any], record))
    return records


def load_seed_aliases(path: Path) -> list[dict[str, Any]]:
    """Read the SQL COPY seed into the same shape as the production registry query."""
    content = path.read_text(encoding="utf-8")
    copy_data = content.split("FROM stdin;\n", 1)[1].split("\n\\.\n", 1)[0]
    rows: list[dict[str, Any]] = []
    for entity_id, line in enumerate(copy_data.splitlines(), start=1):
        canonical_name, _coarse_type, raw_aliases = line.split("\t")
        aliases = [canonical_name, *(value.strip() for value in raw_aliases.split(";"))]
        normalized_seen: set[str] = set()
        for alias in aliases:
            normalized = " ".join(alias.casefold().split())
            if normalized in normalized_seen:
                continue
            normalized_seen.add(normalized)
            rows.append(
                {
                    "entity_id": entity_id,
                    "canonical_name": canonical_name,
                    "monitored": True,
                    "alias": alias,
                    "normalized_alias": normalized,
                }
            )
    return rows


async def _run_pass(
    client: InferenceClient,
    pass_name: PassName,
    request: dict[str, Any],
    source_text: str,
    attempts: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
    entities: Sequence[Mapping[str, Any]] = (),
    claims: Sequence[Mapping[str, Any]] = (),
    post_validate: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    try:
        response = await client.infer(pass_name, request)
    except ModelOutputError as error:
        generation_errors = [{"kind": "generation_failure", "message": str(error)}]
        attempts.append(
            {
                "pass": pass_name,
                "attempt": "primary",
                "raw_output": None,
                "parsed_payload": None,
                "sanitized_payload": None,
                "status": "failed",
                "validation_errors": generation_errors,
                "finish_reason": None,
                "completion_tokens": None,
            }
        )
        diagnostics.append(
            {
                "pass": pass_name,
                "raw_primary_output": None,
                "sanitized_primary_output": None,
                "primary_validation_errors": generation_errors,
                "raw_repair_output": None,
                "sanitized_repair_output": None,
                "repair_validation_errors": [],
                "final_validation_status": "generation_failure",
                "final_parsed_payload": None,
            }
        )
        raise
    payload: dict[str, Any] | None = None
    sanitized_payload: dict[str, Any] | None = None
    try:
        payload = parse_json_object(response.raw_output)
        sanitized_payload = sanitize_pass_payload(pass_name, payload, source_text)
        validate_pass(pass_name, sanitized_payload, source_text, entities, claims)
        if post_validate is not None:
            post_validate(sanitized_payload)
    except InferenceValidationError as error:
        errors = validation_errors(error)
        attempts.append(
            _attempt_record(
                pass_name, "primary", response, payload, sanitized_payload, "invalid", errors
            )
        )
        try:
            repaired = await client.repair(pass_name, response.raw_output, errors)
        except ModelOutputError as repair_error:
            repair_errors = [{"kind": "generation_failure", "message": str(repair_error)}]
            attempts.append(
                {
                    "pass": pass_name,
                    "attempt": "repair",
                    "raw_output": None,
                    "parsed_payload": None,
                    "sanitized_payload": None,
                    "status": "failed",
                    "validation_errors": repair_errors,
                    "finish_reason": None,
                    "completion_tokens": None,
                }
            )
            diagnostics.append(
                _pass_diagnostic(
                    pass_name,
                    response,
                    sanitized_payload,
                    errors,
                    None,
                    None,
                    repair_errors,
                    "generation_failure",
                    None,
                )
            )
            raise
        repaired_payload: dict[str, Any] | None = None
        sanitized_repaired_payload: dict[str, Any] | None = None
        try:
            repaired_payload = parse_json_object(repaired.raw_output)
            sanitized_repaired_payload = sanitize_pass_payload(
                pass_name, repaired_payload, source_text
            )
            validate_pass(pass_name, sanitized_repaired_payload, source_text, entities, claims)
            if post_validate is not None:
                post_validate(sanitized_repaired_payload)
        except InferenceValidationError as repair_error:
            repair_errors = validation_errors(repair_error)
            attempts.append(
                _attempt_record(
                    pass_name,
                    "repair",
                    repaired,
                    repaired_payload,
                    sanitized_repaired_payload,
                    "invalid",
                    repair_errors,
                )
            )
            diagnostics.append(
                _pass_diagnostic(
                    pass_name,
                    response,
                    sanitized_payload,
                    errors,
                    repaired,
                    sanitized_repaired_payload,
                    repair_errors,
                    "invalid",
                    None,
                )
            )
            raise
        assert sanitized_repaired_payload is not None
        attempts.append(
            _attempt_record(
                pass_name,
                "repair",
                repaired,
                repaired_payload,
                sanitized_repaired_payload,
                "valid",
                [],
            )
        )
        diagnostics.append(
            _pass_diagnostic(
                pass_name,
                response,
                sanitized_payload,
                errors,
                repaired,
                sanitized_repaired_payload,
                [],
                "valid",
                sanitized_repaired_payload,
            )
        )
        return sanitized_repaired_payload
    assert sanitized_payload is not None
    attempts.append(
        _attempt_record(pass_name, "primary", response, payload, sanitized_payload, "valid", [])
    )
    diagnostics.append(
        _pass_diagnostic(
            pass_name,
            response,
            sanitized_payload,
            [],
            None,
            None,
            [],
            "valid",
            sanitized_payload,
        )
    )
    return sanitized_payload


def _attempt_record(
    pass_name: PassName,
    attempt: str,
    response: ModelResponse,
    parsed_payload: dict[str, Any] | None,
    sanitized_payload: dict[str, Any] | None,
    status: str,
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "pass": pass_name,
        "attempt": attempt,
        "raw_output": response.raw_output,
        "parsed_payload": parsed_payload,
        "sanitized_payload": sanitized_payload,
        "status": status,
        "validation_errors": errors,
        "finish_reason": response.finish_reason,
        "completion_tokens": response.completion_tokens,
    }


def _pass_diagnostic(
    pass_name: PassName,
    primary: ModelResponse,
    sanitized_primary: dict[str, Any] | None,
    primary_errors: list[dict[str, str]],
    repair: ModelResponse | None,
    sanitized_repair: dict[str, Any] | None,
    repair_errors: list[dict[str, str]],
    final_status: str,
    final_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "pass": pass_name,
        "raw_primary_output": primary.raw_output,
        "sanitized_primary_output": sanitized_primary,
        "primary_validation_errors": primary_errors,
        "raw_repair_output": repair.raw_output if repair is not None else None,
        "sanitized_repair_output": sanitized_repair,
        "repair_validation_errors": repair_errors,
        "final_validation_status": final_status,
        "final_parsed_payload": final_payload,
    }


async def analyze_annotation(
    annotation: Mapping[str, Any], aliases: list[dict[str, Any]], client: InferenceClient
) -> dict[str, Any]:
    """Run the complete target-monitoring pipeline for one golden source."""
    source = cast(Mapping[str, Any], annotation["source"])
    source_text = cast(str, source["text"])
    matched = matched_monitored_entity_ids(source_text, aliases)
    base = {
        "comparison_schema_version": COMPARISON_SCHEMA_VERSION,
        "input": {
            "example_id": annotation["example_id"],
            "post_revision_id": source["post_revision_id"],
            "post_text": source_text,
            "post_length_chars": len(source_text),
        },
        "golden_output": annotation["annotations"],
        "prefilter": {"matched_entity_ids": matched},
        "run_metadata": {
            "model": DEFAULT_MODEL,
            "pipeline_version": "inference_v3_1",
            "run_timestamp": datetime.now(UTC).isoformat(),
        },
    }
    if not matched:
        return base | {
            "status": "filtered_out",
            "attempts": [],
            "pass_diagnostics": [],
            "final_output": None,
        }
    attempts: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    try:

        def validate_resolved(payload: Mapping[str, Any]) -> None:
            resolved = resolve_entity_groups(payload["entities"], aliases)
            if not any(entity["monitored"] for entity in resolved):
                raise InferenceValidationError(
                    [
                        ValidationIssue(
                            "reference_failure",
                            "Pass 1 omitted every monitored actor that admitted the post",
                        )
                    ]
                )

        entity_payload = await _run_pass(
            client,
            "entities",
            {"post_text": source_text},
            source_text,
            attempts,
            diagnostics,
            post_validate=validate_resolved,
        )
        entities = resolve_entity_groups(entity_payload["entities"], aliases)
        claim_payload = await _run_pass(
            client,
            "claims",
            {"post_text": source_text, "entities": entities},
            source_text,
            attempts,
            diagnostics,
            entities,
        )
        claims = assign_claim_ids(claim_payload, source_text)
        classification_payload = await _run_pass(
            client,
            "classification",
            {"items": classification_items(source_text, entities, claims)},
            source_text,
            attempts,
            diagnostics,
            entities,
            claims,
        )
        result = final_payload(entities, claims, classification_payload["classifications"])
    except Exception as error:
        failure = (
            validation_errors(error)
            if isinstance(error, InferenceValidationError)
            else [{"kind": "model_request_failed", "message": str(error)}]
        )
        return base | {
            "status": "failed",
            "attempts": attempts,
            "pass_diagnostics": diagnostics,
            "failure": failure,
            "final_output": None,
        }
    return base | {
        "status": "completed",
        "attempts": attempts,
        "pass_diagnostics": diagnostics,
        "final_output": result,
    }


def completed_example_ids(path: Path) -> set[str]:
    """Return already persisted comparison IDs for resumable generation."""
    if not path.exists():
        return set()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    identifiers = [row["input"]["example_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("comparison output contains duplicate example IDs")
    return set(identifiers)


async def generate_comparisons(
    annotations: Sequence[Mapping[str, Any]],
    aliases: list[dict[str, Any]],
    output_path: Path,
    client: InferenceClient,
    logger: logging.Logger,
    concurrency: int = 1,
) -> tuple[int, int]:
    """Append missing full-pipeline records and return written/failed counts."""
    if concurrency < 1:
        raise ValueError("concurrency must be at least one")
    completed = completed_example_ids(output_path)
    pending = [item for item in annotations if item["example_id"] not in completed]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = failures = 0
    with output_path.open("a", encoding="utf-8") as output:
        for batch in batched(pending, concurrency):
            rows = await asyncio.gather(
                *(analyze_annotation(annotation, aliases, client) for annotation in batch)
            )
            for annotation, row in zip(batch, rows):
                output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                output.flush()
                written += 1
                failures += row["status"] == "failed"
                logger.info(
                    "comparison row written",
                    extra={"example_id": annotation["example_id"], "status": row["status"]},
                )
    return written, failures


def validate_comparisons(path: Path) -> int:
    """Validate record identity and grounded final outputs."""
    identifiers: set[str] = set()
    count = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        row = json.loads(line)
        identifier = row.get("input", {}).get("example_id")
        if not isinstance(identifier, str) or identifier in identifiers:
            raise ValueError(f"invalid or duplicate example ID on line {line_number}")
        if row.get("comparison_schema_version") != COMPARISON_SCHEMA_VERSION:
            raise ValueError(f"wrong schema version on line {line_number}")
        if row.get("status") == "filtered_out" and row.get("attempts"):
            raise ValueError(f"filtered record has attempts on line {line_number}")
        identifiers.add(identifier)
        count += 1
    return count


def summarize_comparisons(path: Path) -> dict[str, Any]:
    """Calculate deterministic contract-health metrics for one comparison artifact."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    status_counts = {
        status: sum(row.get("status") == status for row in rows)
        for status in ("filtered_out", "failed", "completed")
    }
    pass_metrics: dict[str, dict[str, int]] = {}
    for pass_name in ("entities", "claims"):
        pass_metrics[pass_name] = {
            "primary_valid": sum(
                any(
                    attempt["pass"] == pass_name
                    and attempt["attempt"] == "primary"
                    and attempt["status"] == "valid"
                    for attempt in row.get("attempts", [])
                )
                for row in rows
            ),
            "valid_after_repair": sum(
                any(
                    attempt["pass"] == pass_name
                    and attempt["attempt"] == "repair"
                    and attempt["status"] == "valid"
                    for attempt in row.get("attempts", [])
                )
                for row in rows
            ),
        }
    pass_metrics["classification"] = {
        "valid": sum(
            any(
                attempt["pass"] == "classification" and attempt["status"] == "valid"
                for attempt in row.get("attempts", [])
            )
            for row in rows
        )
    }
    failure_kinds = (
        "json_parse_failure",
        "schema_failure",
        "grounding_failure",
        "reference_failure",
    )
    failure_reasons = {
        kind: sum(
            any(
                error.get("kind") == kind
                for attempt in row.get("attempts", [])
                for error in attempt.get("validation_errors", [])
            )
            for row in rows
        )
        for kind in failure_kinds
    }
    return {
        "examples": len(rows),
        "status": status_counts,
        "passes": pass_metrics,
        "failure_reasons": failure_reasons,
    }


def compare_summaries(current: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    """Return current/baseline metrics and signed deltas for review."""
    current_status = cast(Mapping[str, int], current["status"])
    baseline_status = cast(Mapping[str, int], baseline["status"])
    current_reasons = cast(Mapping[str, int], current["failure_reasons"])
    baseline_reasons = cast(Mapping[str, int], baseline["failure_reasons"])
    return {
        "current": current,
        "baseline": baseline,
        "delta": {
            "status": {key: current_status[key] - baseline_status[key] for key in current_status},
            "failure_reasons": {
                key: current_reasons[key] - baseline_reasons[key] for key in current_reasons
            },
        },
    }


def parse_args(arguments: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Mamay inference-v3 comparisons")
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--registry-seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=os.environ.get("LITELLM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args(arguments)


async def run(arguments: Iterable[str] | None = None) -> None:
    """Run or validate the resumable v3 comparison artifact."""
    args = parse_args(arguments)
    if args.validate_only:
        validate_comparisons(args.output)
        return
    api_key = os.environ.get("LITELLM_API_KEY")
    if not api_key:
        raise RuntimeError("LITELLM_API_KEY must be configured for the comparison run")
    client = LiteLlmInferenceClient(
        args.base_url,
        api_key,
        args.model,
        args.timeout_seconds,
        args.max_output_tokens,
    )
    try:
        await generate_comparisons(
            load_annotations(args.annotations),
            load_seed_aliases(args.registry_seed),
            args.output,
            client,
            setup_logging("telegram-monitor-mamay-golden-v2-experiment"),
            args.concurrency,
        )
        current = summarize_comparisons(args.output)
        comparison = (
            compare_summaries(current, summarize_comparisons(args.baseline))
            if args.baseline.exists()
            else {"current": current, "baseline": None, "delta": None}
        )
        args.output.with_name("summary.json").write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    finally:
        await client.close()


def main() -> None:
    """Run the comparison CLI."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
