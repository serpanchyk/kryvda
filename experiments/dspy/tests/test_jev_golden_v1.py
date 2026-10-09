"""Tests for the classification-only Jev golden comparison."""

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest
from golden_schema import load_golden
from jev_golden_v1 import (
    PROMPTS,
    SEPARATOR,
    ClaimDecision,
    OpenRouterDecisionClient,
    PairDecision,
    analyze_record,
    author_label,
    build_questions,
    build_requests,
    calibrated_stance,
    decode_answers,
    decomposed_stance,
    entity_names,
    extended_report,
    extended_rhetoric_gold,
    generate_responses,
    main_rhetoric,
    negative_stance_auc,
    production_prediction,
    production_rhetoric,
    select_examples,
    usage_summary,
    validate_rows,
)

TEXT = "Вступ. Фонд — грантоїди. Суддя ухвалив рішення. Кінець."


def record(identifier: str = "golden_v0-001") -> dict[str, Any]:
    """Return a two-claim v0 record with an unmapped rhetoric label."""
    return {
        "schema_version": "annotation_schema_v1",
        "example_id": identifier,
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
                    "canonical_name": None,
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
                },
                {
                    "id": "c2",
                    "normalized_text": "Суддя ухвалив рішення.",
                    "entity_ids": ["e2"],
                    "evidence_spans": [{"start": 25, "end": 47}],
                    "attribution": {"source_kind": "named_entity", "source_entity_id": "e1"},
                    "presentation": "reported",
                    "epistemic_status": "denied",
                },
            ],
            "stances": [
                {
                    "entity_id": "e1",
                    "perspective": {"source_kind": "channel_editorial"},
                    "value": "negative",
                    "evidence_spans": [{"start": 7, "end": 24}],
                },
                {
                    "entity_id": "e2",
                    "perspective": {"source_kind": "named_entity", "source_entity_id": "e1"},
                    "value": "neutral",
                    "evidence_spans": [{"start": 25, "end": 47}],
                },
            ],
            "rhetorical_features": [
                {
                    "feature_type": "grant_discrediting",
                    "target_entity_id": "e1",
                    "target_claim_id": "c1",
                },
                {
                    "feature_type": "derogatory_labeling",
                    "target_entity_id": "e1",
                    "evidence_span": {"start": 7, "end": 24},
                },
                {"feature_type": "ridicule", "target_entity_id": None},
            ],
        },
    }


def answers_for(request: Mapping[str, Any]) -> dict[str, Any]:
    """Answer every question deterministically: negative stance, strong grant discrediting."""
    answers: dict[str, Any] = {}
    for key, question in request["questions"].items():
        if question["type"] == "noul":
            answers[key] = {
                "type": "noul",
                "noul": 0.9 if key.endswith("grant_discrediting") else 0.1,
            }
        elif key.endswith("stance"):
            answers[key] = {
                "type": "choice",
                "choice": "негативне",
                "probabilities": {"позитивне": 0.0, "негативне": 0.8, "відсутнє": 0.2},
            }
        else:
            choice = "asserted" if key.endswith("epistemic") else "editorial"
            answers[key] = {"type": "choice", "choice": choice, "probabilities": {choice: 1.0}}
    return answers


class FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.requests: list[Mapping[str, Any]] = []

    async def decide(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self.requests.append(request)
        if self.fail:
            raise httpx.ConnectError("offline")
        return {
            "model": "typesafe/jev-test",
            "answers": answers_for(request),
            "usage": {"input_tokens": 10, "output_tokens": 2, "cost": 0.001},
        }


def test_questions_cover_claims_pairs_and_every_rhetoric_label() -> None:
    golden = load_golden(record())
    questions = build_questions(golden, entity_names(record()))
    assert f"c1{SEPARATOR}epistemic" in questions
    assert f"c2{SEPARATOR}presentation" in questions
    assert f"c1{SEPARATOR}e1{SEPARATOR}stance" in questions
    assert f"c1{SEPARATOR}e1{SEPARATOR}rhetoric{SEPARATOR}call_for_punishment" in questions
    assert len(questions) == 2 * 2 + 2 * 10


def test_requests_keep_claim_questions_together_and_carry_local_context() -> None:
    golden = load_golden(record())
    requests = build_requests(golden, entity_names(record()), "jev", max_questions=12)
    assert len(requests) == 2
    first = requests[0]
    assert set(first["state"]["claims"]) == {"c1"}
    assert (
        first["state"]["claims"]["c1"]["context"]
        == "Вступ. Фонд — грантоїди. Суддя ухвалив рішення."
    )
    assert requests[1]["state"]["claims"]["c2"]["author"] == "названий актор: Фонд"
    with pytest.raises(ValueError, match="max_questions"):
        build_requests(golden, {}, "jev", 0)


def test_author_label_falls_back_for_unknown_sources() -> None:
    assert author_label({"source_kind": "named_entity"}, {}) == "названий актор"
    assert author_label({"source_kind": "unknown"}, {}) == "невідоме джерело"
    assert author_label({"source_kind": "channel_editorial"}, {}) == "редакція каналу"


def test_decode_and_project_to_production_taxonomy() -> None:
    golden = load_golden(record())
    request = build_requests(golden, entity_names(record()), "jev", 100)[0]
    pairs, claims = decode_answers(answers_for(request))
    assert claims["c2"] == ClaimDecision("asserted", "editorial")
    assert pairs[("c1", "e1")].rhetoric["grant_discrediting"] == 0.9
    prediction = production_prediction(golden, pairs, claims, threshold=0.5)
    assert prediction.claims[0].epistemic_status == "ствердження"
    assert [item.rhetoric for item in prediction.classifications] == [[], []]
    restricted = production_prediction(
        golden, pairs, claims, 0.05, allowed_pairs={("c2", "e2")}, allowed_claims={"c2"}
    )
    assert [item.claim_id for item in restricted.classifications] == ["c2"]
    assert [claim.id for claim in restricted.claims] == ["c2"]


def test_production_rhetoric_merges_gates_and_caps() -> None:
    decision = PairDecision(
        "негативне",
        {},
        {"ridicule": 0.6, "derogatory_labeling": 0.9, "delegitimization": 0.7, "crime": 0.99},
    )
    assert production_rhetoric(decision, 0.5) == [
        "висміювання_або_особиста_образа",
        "делегітимізація",
    ]
    assert production_rhetoric(decision, 0.5, cap=None)[-1] == "делегітимізація"
    neutral = PairDecision("відсутнє", {}, decision.rhetoric)
    assert production_rhetoric(neutral, 0.5) == []
    assert production_rhetoric(neutral, 0.5, gated=False)


@pytest.mark.parametrize(
    ("choice", "probabilities", "threshold", "expected"),
    [
        ("відсутнє", {"негативне": 0.05, "відсутнє": 0.95}, 0.02, "негативне"),
        ("відсутнє", {"негативне": 0.01, "відсутнє": 0.99}, 0.02, "відсутнє"),
        ("негативне", {"негативне": 0.4, "позитивне": 0.35, "відсутнє": 0.25}, 0.5, "позитивне"),
        ("негативне", {"негативне": 0.9}, None, "негативне"),
    ],
)
def test_calibrated_stance(
    choice: str, probabilities: dict[str, float], threshold: float | None, expected: str
) -> None:
    decision = PairDecision(choice, probabilities, {})
    assert calibrated_stance(decision, threshold).stance == expected


def test_extended_gold_keeps_unmapped_labels_and_reports_them() -> None:
    golden = load_golden(record())
    gold = extended_rhetoric_gold(record(), golden)
    assert gold[("c1", "e1")] == {"grant_discrediting", "derogatory_labeling"}
    assert gold[("c2", "e2")] == set()
    request_answers: dict[str, Any] = {}
    for request in build_requests(golden, entity_names(record()), "jev", 100):
        request_answers |= answers_for(request)
    pairs, claims = decode_answers(request_answers)
    report = extended_report([(record(), golden, pairs, claims)], 0.5)
    grant = report["rhetoric_ungated"]["per_label"]["grant_discrediting"]
    assert grant["recall"] == 1.0 and grant["support"] == 1
    assert report["epistemic"]["per_class"]["denied"]["support"] == 1
    assert report["presentation"]["accuracy"] == 0.5


def test_negative_stance_auc_ranks_reviewed_negatives() -> None:
    golden = load_golden(record())
    pairs = {
        ("c1", "e1"): PairDecision("відсутнє", {"негативне": 0.3}, {}),
        ("c2", "e2"): PairDecision("відсутнє", {"негативне": 0.1}, {}),
    }
    assert negative_stance_auc([(golden, pairs, {})]) == 1.0


async def test_generation_is_resumable_and_validated(tmp_path: Path) -> None:
    output = tmp_path / "responses.jsonl"
    client = FakeClient()
    logger = logging.getLogger("test")
    assert await generate_responses([record()], output, client, logger, max_questions=12) == (1, 0)
    assert await generate_responses([record()], output, client, logger) == (0, 0)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    validate_rows(rows, [record()])
    summary = usage_summary(rows)
    assert summary["requests"] == 2 and summary["cost_usd"] == pytest.approx(0.002)
    with pytest.raises(ValueError, match="exactly one row"):
        validate_rows(rows, [record(), record("golden_v0-002")])
    with pytest.raises(ValueError, match="concurrency"):
        await generate_responses([record()], output, client, logger, concurrency=0)


async def test_failed_requests_are_recorded_and_rejected_by_validation() -> None:
    row = await analyze_record(record(), FakeClient(fail=True), "jev", 100)
    assert row["status"] == "failed" and "ConnectError" in row["error"]
    with pytest.raises(ValueError, match="did not complete"):
        validate_rows([row], [record()])


async def test_openrouter_client_retries_transient_status() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"answers": {}})

    client = OpenRouterDecisionClient(
        "https://decisions.test",
        "secret",
        backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        assert await client.decide({"questions": {}}) == {"answers": {}}
    finally:
        await client.close()
    assert len(calls) == 2
    assert calls[0].headers["Authorization"] == "Bearer secret"


async def test_openrouter_client_raises_client_errors_without_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": "bad"})

    client = OpenRouterDecisionClient(
        "https://decisions.test",
        "secret",
        backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.decide({})
    finally:
        await client.close()
    assert calls == 1


def test_v4_questions_decompose_stance_and_ask_one_main_device() -> None:
    golden = load_golden(record())
    questions = build_questions(golden, entity_names(record()), PROMPTS["v4"])
    prefix = f"c1{SEPARATOR}e1{SEPARATOR}"
    assert {f"{prefix}own_negative", f"{prefix}own_positive", f"{prefix}rhetoric_main"} <= set(
        questions
    )
    assert f"{prefix}stance" not in questions
    assert "none" in questions[f"{prefix}rhetoric_main"]["criteria"]
    assert len(questions) == 2 * 2 + 2 * 3
    request = build_requests(golden, entity_names(record()), "jev", 100, PROMPTS["v4"])[0]
    assert request["state"]["guidelines"] == PROMPTS["v4"].guidelines


def test_v4_answers_decode_into_stance_and_main_rhetoric() -> None:
    prefix = f"c1{SEPARATOR}e1{SEPARATOR}"
    pairs, _ = decode_answers(
        {
            f"{prefix}own_negative": {"type": "noul", "noul": 0.8},
            f"{prefix}own_positive": {"type": "noul", "noul": 0.1},
            f"{prefix}rhetoric_main": {
                "type": "choice",
                "choice": "grant_discrediting",
                "probabilities": {"grant_discrediting": 0.6, "ridicule": 0.3, "none": 0.1},
            },
        }
    )
    decision = pairs[("c1", "e1")]
    assert decision.stance == "негативне"
    assert decision.rhetoric == {"grant_discrediting": 1.0, "ridicule": 1.0}
    assert decision.stance_probabilities["відсутнє"] == pytest.approx(0.2)


@pytest.mark.parametrize(
    ("negative", "positive", "expected"),
    [
        (0.7, 0.6, "негативне"),
        (0.4, 0.6, "позитивне"),
        (0.4, 0.3, "відсутнє"),
        (0.6, 0.9, "позитивне"),
    ],
)
def test_decomposed_stance(negative: float, positive: float, expected: str) -> None:
    assert decomposed_stance(negative, positive, {}).stance == expected


def test_main_rhetoric_respects_none_and_runner_up_floor() -> None:
    assert main_rhetoric({"choice": "none", "probabilities": {"none": 0.9}}) == {}
    answer = {
        "choice": "ridicule",
        "probabilities": {"ridicule": 0.7, "delegitimization": 0.2, "none": 0.1},
    }
    assert main_rhetoric(answer) == {"ridicule": 1.0}


def test_select_examples_partitions_by_old55() -> None:
    records = [record("a"), record("b")]
    assert [item["example_id"] for item in select_examples(records, "old55", {"a"})] == ["a"]
    assert [item["example_id"] for item in select_examples(records, "diagnostic45", {"a"})] == ["b"]
    assert len(select_examples(records, "all", set())) == 2


async def test_rows_record_and_validate_their_prompt_version(tmp_path: Path) -> None:
    output = tmp_path / "responses.jsonl"
    await generate_responses(
        [record()], output, FakeClient(), logging.getLogger("test"), prompt_version="v4"
    )
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["prompt_version"] == "v4"
    validate_rows(rows, [record()])
