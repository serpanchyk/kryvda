"""Tests for the auditable inference-v3 comparison runner."""

import json
import logging
from pathlib import Path
from typing import Any

from mamay_golden_v2 import (
    analyze_annotation,
    completed_example_ids,
    generate_comparisons,
    is_transient_failure,
    load_seed_aliases,
    select_split,
    summarize_comparisons,
    validate_comparisons,
)
from telegram_monitor_ai_worker.models import ModelResponse

TEXT = "Шабунін працює."
ALIASES = [
    {
        "entity_id": 1,
        "canonical_name": "Віталій Шабунін",
        "monitored": True,
        "alias": "Шабунін",
        "normalized_alias": "шабунін",
    }
]


def annotation(identifier: str = "golden-1", text: str = TEXT) -> dict[str, Any]:
    return {
        "example_id": identifier,
        "source": {"post_revision_id": 7, "text": text},
        "annotations": {"entities": [], "stances": [], "claims": []},
    }


class FakeClient:
    def __init__(self) -> None:
        self.payloads = {
            "candidates": {"candidates": {"r1": {"reason": "прізвище", "same_actor": True}}},
            "entities": {"entities": []},
            "claims": {
                "claims": [
                    {
                        "normalized_text": "Віталій Шабунін працює.",
                        "entity_ids": ["e1"],
                        "evidence_text": TEXT,
                        "attribution": {
                            "source_kind": "channel_editorial",
                            "source_entity_id": None,
                        },
                        "epistemic_status": "ствердження",
                    }
                ]
            },
            "targets": {"claims": {"c1": {"reason": "Шабунін", "evaluated": ["Віталій Шабунін"]}}},
            "classification": {
                "classifications": [
                    {
                        "claim_id": "c1",
                        "entity_id": "e1",
                        "stance": "відсутнє",
                        "rhetoric": [],
                    }
                ]
            },
        }

    async def infer(self, name: str, request: dict[str, Any]) -> ModelResponse:
        return ModelResponse(json.dumps(self.payloads[name], ensure_ascii=False), 1)

    async def repair(self, name: str, original: str, errors: list[dict[str, str]]) -> ModelResponse:
        return ModelResponse(json.dumps(self.payloads[name], ensure_ascii=False), 1)


async def test_analysis_records_prefilter_all_passes_and_final_output() -> None:
    row = await analyze_annotation(annotation(), ALIASES, FakeClient())

    assert row["status"] == "completed"
    assert row["input"]["post_length_chars"] == len(TEXT)
    assert [attempt["pass"] for attempt in row["attempts"]] == [
        "candidates",
        "entities",
        "claims",
        "targets",
        "classification",
    ]
    assert row["final_output"]["pipeline_version"] == "inference_v4"
    assert len(row["pass_diagnostics"]) == 5
    assert row["pass_diagnostics"][1]["sanitized_primary_output"] == {"entities": []}
    assert row["final_output"]["entities"][0]["canonical_name"] == "Віталій Шабунін"


async def test_filtered_records_make_no_model_requests() -> None:
    row = await analyze_annotation(annotation(text="Без збігів."), ALIASES, FakeClient())
    assert row["status"] == "filtered_out"
    assert row["attempts"] == []


async def test_generator_resumes_and_validator_checks_artifact(tmp_path: Path) -> None:
    output = tmp_path / "comparisons.jsonl"
    written, failures = await generate_comparisons(
        [annotation()], ALIASES, output, FakeClient(), logging.getLogger("test")
    )
    assert (written, failures) == (1, 0)
    assert validate_comparisons(output) == 1
    assert completed_example_ids(output) == {"golden-1"}
    assert summarize_comparisons(output) == {
        "examples": 1,
        "status": {
            "filtered_out": 0,
            "failed": 0,
            "completed": 1,
            "completed_with_partial_classification": 0,
            "completed_with_entity_fallback": 0,
        },
        "passes": {
            "entities": {"primary_valid": 1, "valid_after_repair": 0, "salvaged": 0},
            "claims": {"primary_valid": 1, "valid_after_repair": 0, "salvaged": 0},
            "classification": {
                "expected_pairs": 1,
                "primary_valid_pairs": 1,
                "salvaged_pairs": 0,
                "retry_recovered_pairs": 0,
                "complete": 1,
                "partial": 0,
                "pair_retries": 0,
                "permanently_failed_pairs": 0,
            },
        },
        "failure_reasons": {
            "json_parse_failure": 0,
            "schema_failure": 0,
            "grounding_failure": 0,
            "reference_failure": 0,
        },
        "sanitization_actions": {},
    }
    assert await generate_comparisons(
        [annotation()], ALIASES, output, FakeClient(), logging.getLogger("test")
    ) == (0, 0)


def test_seed_loader_reads_supplied_copy_registry(tmp_path: Path) -> None:
    seed = tmp_path / "seed.sql"
    seed.write_text(
        "COPY x FROM stdin;\nШабунін\tperson\tШабунін; Shabunin\n\\.\n",
        encoding="utf-8",
    )
    aliases = load_seed_aliases(seed)
    assert [row["alias"] for row in aliases] == ["Шабунін", "Shabunin"]


class FlakyClient(FakeClient):
    """Fail the first request with a provider 503, then answer normally."""

    def __init__(self, failures: int = 1, message: str = "Error code: 503 - unavailable") -> None:
        super().__init__()
        self.failures = failures
        self.message = message

    async def infer(self, name: str, request: dict[str, Any]) -> ModelResponse:
        if self.failures:
            self.failures -= 1
            raise RuntimeError(self.message)
        return await super().infer(name, request)


async def test_generator_retries_transient_provider_errors(tmp_path: Path) -> None:
    output = tmp_path / "comparisons.jsonl"

    written, failures = await generate_comparisons(
        [annotation()],
        ALIASES,
        output,
        FlakyClient(),
        logging.getLogger("test"),
        retry_delay_seconds=0,
    )

    assert (written, failures) == (1, 0)
    assert json.loads(output.read_text())["status"] == "completed"


async def test_generator_writes_non_transient_failures_without_retry(tmp_path: Path) -> None:
    output = tmp_path / "comparisons.jsonl"
    client = FlakyClient(failures=1, message="Error code: 400 - bad schema")

    written, failures = await generate_comparisons(
        [annotation(), annotation("golden-2")],
        ALIASES,
        output,
        client,
        logging.getLogger("test"),
        concurrency=2,
        retry_delay_seconds=0,
    )

    assert (written, failures) == (2, 1)
    assert completed_example_ids(output) == {"golden-1", "golden-2"}


def test_transient_failure_detection_needs_a_provider_error() -> None:
    def failed(message: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "failure": [{"kind": "model_request_failed", "message": message}],
        }

    assert is_transient_failure(failed("Error code: 429 - slow down"))
    assert is_transient_failure(failed("Request timed out."))
    assert not is_transient_failure(failed("Error code: 400 - bad request"))
    assert not is_transient_failure({"status": "completed"})


def test_select_split_separates_the_measure_only_test_examples() -> None:
    records = [{"example_id": name} for name in ("a", "b", "c")]

    assert select_split(records, "all", {"b"}) == records
    assert select_split(records, "dev", {"b"}) == [{"example_id": "a"}, {"example_id": "c"}]
    assert select_split(records, "test", {"b"}) == [{"example_id": "b"}]
