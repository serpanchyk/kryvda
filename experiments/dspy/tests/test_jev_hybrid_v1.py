"""Tests for the hybrid Mamay extraction plus Jev classification comparison."""

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest
from jev_golden_v1 import SEPARATOR, ClaimDecision, PairDecision
from jev_hybrid_v1 import (
    analyze_row,
    build_summary,
    generate_responses,
    hybrid_output,
    mamay_claim_set,
    stance_agreement,
    validate_rows,
    with_mamay_stance,
)

TEXT = "Вступ. Фонд — грантоїди. Суддя ухвалив рішення."


def annotation() -> dict[str, Any]:
    """Return a reviewed v0 record whose claims Mamay reproduces."""
    return {
        "schema_version": "annotation_schema_v1",
        "example_id": "golden_v0-001",
        "source": {"text": TEXT},
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "surface_form": "Фонд",
                    "canonical_name": "Фонд",
                    "registry_status": "monitored",
                },
                {
                    "id": "e2",
                    "surface_form": "Суддя",
                    "canonical_name": "Суддя",
                    "registry_status": "monitored",
                },
            ],
            "claims": [
                {
                    "id": "c1",
                    "normalized_text": "Фонд — грантоїди.",
                    "entity_ids": ["e1"],
                    "evidence_spans": [{"start": 7, "end": 24}],
                    "attribution": {"source_kind": "channel_editorial"},
                    "presentation": "editorial",
                    "epistemic_status": "asserted",
                }
            ],
            "stances": [
                {
                    "entity_id": "e1",
                    "perspective": {"source_kind": "channel_editorial"},
                    "value": "negative",
                    "evidence_spans": [{"start": 7, "end": 24}],
                }
            ],
            "rhetorical_features": [
                {
                    "feature_type": "derogatory_labeling",
                    "target_entity_id": "e1",
                    "target_claim_id": "c1",
                }
            ],
        },
    }


def mamay_row(stance: str = "відсутнє") -> dict[str, Any]:
    """Return a recorded Mamay v3.6 row with one claim and one monitored target."""
    return {
        "input": {"example_id": "golden_v0-001"},
        "status": "completed",
        "final_output": {
            "pipeline_version": "inference_v3_6",
            "status": "completed",
            "entities": [
                {"id": "e1", "mentions": ["Фонд"], "canonical_name": "Фонд", "monitored": True},
                {"id": "e2", "mentions": ["Суддя"], "canonical_name": None, "monitored": False},
            ],
            "claims": [
                {
                    "id": "c1",
                    "normalized_text": "Фонд — грантоїди.",
                    "entity_ids": ["e1", "e2"],
                    "evidence_text": "Фонд — грантоїди.",
                    "attribution": {"source_entity_id": None, "source_kind": "channel_editorial"},
                    "epistemic_status": "ствердження",
                    "evidence_start": 7,
                    "evidence_end": 24,
                }
            ],
            "classifications": [
                {"claim_id": "c1", "entity_id": "e1", "stance": stance, "rhetoric": []}
            ],
        },
    }


def answers_for(request: Mapping[str, Any]) -> dict[str, Any]:
    """Answer v4 questions with a negative stance and a ridicule main device."""
    answers: dict[str, Any] = {}
    for key, question in request["questions"].items():
        if key.endswith("own_negative"):
            answers[key] = {"type": "noul", "noul": 0.9}
        elif key.endswith("own_positive"):
            answers[key] = {"type": "noul", "noul": 0.05}
        elif key.endswith("rhetoric_main"):
            answers[key] = {
                "type": "choice",
                "choice": "derogatory_labeling",
                "probabilities": {"derogatory_labeling": 0.8, "none": 0.2},
            }
        else:
            choice = "alleged" if key.endswith("epistemic") else "editorial"
            answers[key] = {"type": "choice", "choice": choice, "probabilities": {choice: 1.0}}
    return answers


class FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def decide(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self.calls += 1
        if self.fail:
            raise httpx.ConnectError("offline")
        return {"model": "jev-test", "answers": answers_for(request), "usage": {"cost": 0.001}}


def test_claim_set_keeps_mamay_claims_and_only_monitored_pairs() -> None:
    claim_set, names = mamay_claim_set(mamay_row()["final_output"], TEXT, "golden_v0-001")
    assert [(item.claim_id, item.entity_id) for item in claim_set.classifications] == [("c1", "e1")]
    assert claim_set.claims[0].evidence_start == 7
    assert names == {"e1": "Фонд", "e2": "Суддя"}


def test_hybrid_output_swaps_classifications_and_optionally_epistemic() -> None:
    final_output = mamay_row()["final_output"]
    pairs = {("c1", "e1"): PairDecision("негативне", {}, {"derogatory_labeling": 1.0})}
    claims = {"c1": ClaimDecision("denied", "editorial")}
    output = hybrid_output(final_output, pairs, claims)
    assert output["classifications"] == [
        {
            "claim_id": "c1",
            "entity_id": "e1",
            "stance": "негативне",
            "rhetoric": ["висміювання_або_особиста_образа"],
        }
    ]
    assert final_output["classifications"][0]["stance"] == "відсутнє"
    unmapped = hybrid_output(final_output, pairs, claims, replace_epistemic=True)
    assert unmapped["claims"][0]["epistemic_status"] == "ствердження"
    alleged = {"c1": ClaimDecision("alleged", "editorial")}
    mapped = hybrid_output(final_output, pairs, alleged, replace_epistemic=True)
    assert mapped["claims"][0]["epistemic_status"] == "невпевнене"


def test_with_mamay_stance_keeps_jev_rhetoric() -> None:
    pairs = {("c1", "e1"): PairDecision("відсутнє", {}, {"ridicule": 1.0})}
    mixed = with_mamay_stance(mamay_row("негативне")["final_output"], pairs)
    assert mixed[("c1", "e1")].stance == "негативне"
    assert mixed[("c1", "e1")].rhetoric == {"ridicule": 1.0}


async def test_generation_validation_and_summary(tmp_path: Path) -> None:
    output = tmp_path / "responses.jsonl"
    rows_in = [mamay_row(), {"input": {"example_id": "golden_v0-002"}, "final_output": None}]
    sources = {"golden_v0-001": TEXT}
    client = FakeClient()
    logger = logging.getLogger("test")
    assert await generate_responses(rows_in, sources, output, client, logger) == (1, 0)
    assert await generate_responses(rows_in, sources, output, client, logger) == (0, 0)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    validate_rows(rows, rows_in, sources)
    old55 = tmp_path / "old55.jsonl"
    old55.write_text(
        json.dumps({"input": {"example_id": "golden_v0-001"}}) + "\n", encoding="utf-8"
    )
    summary = build_summary(rows, [mamay_row()], [annotation()], tmp_path / "a.jsonl", old55)
    mamay = summary["mamay_v3_6"]["old55"]["stance"]["негативне"]
    hybrid = summary["hybrid_jev_pass3"]["old55"]["stance"]["негативне"]
    assert mamay["recall"] == 0.0 and hybrid["recall"] == 1.0
    assert summary["hybrid_jev_pass3"]["old55"]["rhetoric_micro_f1"] == 1.0
    assert summary["mamay_stance_and_jev_rhetoric"]["old55"]["rhetoric_micro_f1"] == 0.0
    assert summary["stance_agreement_on_mamay_pairs"]["agreement"] == 0.0
    with pytest.raises(ValueError, match="concurrency"):
        await generate_responses(rows_in, sources, output, client, logger, concurrency=0)


async def test_failures_are_recorded_and_rejected() -> None:
    row = await analyze_row(mamay_row(), TEXT, FakeClient(fail=True), "jev", 80, "v4")
    assert row["status"] == "failed"
    with pytest.raises(ValueError, match="did not complete"):
        validate_rows([row], [mamay_row()], {"golden_v0-001": TEXT})
    with pytest.raises(ValueError, match="exactly one row"):
        validate_rows([], [mamay_row()], {"golden_v0-001": TEXT})


def test_validation_requires_every_answer() -> None:
    row = {
        "input": {"example_id": "golden_v0-001"},
        "status": "completed",
        "prompt_version": "v4",
        "responses": [{"body": {"answers": {f"c1{SEPARATOR}epistemic": {"choice": "asserted"}}}}],
    }
    with pytest.raises(ValueError, match="missing typed answers"):
        validate_rows([row], [mamay_row()], {"golden_v0-001": TEXT})


def test_stance_agreement_ignores_examples_without_jev_rows() -> None:
    assert stance_agreement([mamay_row()], [])["pairs"] == 0
