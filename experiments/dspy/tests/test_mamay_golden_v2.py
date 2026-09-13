"""Tests for the auditable inference-v3 comparison runner."""

import json
import logging
from pathlib import Path
from typing import Any

from mamay_golden_v2 import (
    analyze_annotation,
    completed_example_ids,
    generate_comparisons,
    load_seed_aliases,
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
            "entities": {"entities": [{"mentions": ["Шабунін"]}]},
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
        "entities",
        "claims",
        "classification",
    ]
    assert row["final_output"]["pipeline_version"] == "inference_v3_4"
    assert len(row["pass_diagnostics"]) == 3
    assert row["pass_diagnostics"][0]["sanitized_primary_output"] == {
        "entities": [{"mentions": ["Шабунін"]}]
    }


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
            "entities": {"primary_valid": 1, "valid_after_repair": 0},
            "claims": {"primary_valid": 1, "valid_after_repair": 0},
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
