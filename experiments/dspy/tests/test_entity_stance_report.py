"""Tests for post x registry-entity stance scoring."""

from __future__ import annotations

from typing import Any

import pytest
from entity_stance_report import (
    MeasureOnlySplitError,
    PostCounts,
    StanceReport,
    f1,
    golden_stances,
    interval,
    loss_stage,
    normalize_name,
    post_counts,
    predicted_stances,
    registry_names,
)
from golden_schema import CanonicalGolden, GoldenClassification, GoldenEntity

NAMES = registry_names(
    [
        {"canonical_name": "Дар'я Каленюк", "alias": "Каленюк"},
        {"canonical_name": "Центр протидії корупції", "alias": "ЦПК"},
    ]
)


def golden() -> CanonicalGolden:
    entities = [
        GoldenEntity("g1", "local-1", "Дарія Каленюк", True),
        GoldenEntity("g2", "local-2", "ЦПК", True),
        GoldenEntity("g3", "local-3", "Хтось Інший", True),
    ]
    classifications = [
        GoldenClassification("c1", "g1", "негативне", []),
        GoldenClassification("c1", "g2", "відсутнє", []),
        GoldenClassification("c1", "g3", "негативне", []),
    ]
    return CanonicalGolden("golden_v0-001", "text", entities, [], classifications, "v1")


def row(stance: str = "негативне") -> dict[str, Any]:
    return {
        "input": {"example_id": "golden_v0-001"},
        "status": "completed",
        "final_output": {
            "entities": [
                {"id": "e1", "canonical_name": "Дар'я Каленюк", "monitored": True},
                {"id": "e2", "canonical_name": "Центр протидії корупції", "monitored": True},
            ],
            "claims": [
                {
                    "id": "c1",
                    "entity_ids": ["e1", "e2"],
                    "evidence_text": "Каленюк і ЦПК",
                    "attribution": {"source_kind": "channel_editorial"},
                }
            ],
            "classifications": [
                {"claim_id": "c1", "entity_id": "e1", "stance": stance},
                {"claim_id": "c1", "entity_id": "e2", "stance": "негативне"},
            ],
        },
    }


def test_golden_names_map_to_the_registry_through_aliases_and_variants() -> None:
    assert normalize_name("Дар’я  Каленюк") == "дар'я каленюк"
    assert golden_stances(golden(), NAMES) == {
        "Дар'я Каленюк": {"негативне"},
        "Центр протидії корупції": {"відсутнє"},
    }


def test_post_counts_score_every_registry_entity_of_the_post() -> None:
    predicted = predicted_stances(row())

    counts = post_counts(golden_stances(golden(), NAMES), predicted, "негативне")

    assert counts == PostCounts(tp=1, fp=1, fn=0)
    assert f1([counts, PostCounts(tp=1, fp=0, fn=1)]) == pytest.approx((2 / 3, 2 / 3, 2 / 3))
    assert interval([float(value) for value in range(100)]) == (2.0, 96.0)


def test_loss_stage_names_where_a_reviewed_stance_was_lost() -> None:
    lost = row("відсутнє")
    predicted = predicted_stances(lost)

    assert loss_stage("Дар'я Каленюк", "негативне", lost, predicted) == "3 claim, other stance"
    assert loss_stage("Дар'я Каленюк", "негативне", row(), predicted_stances(row())) == (
        "4 correct"
    )
    assert loss_stage("Невідомий", "негативне", lost, predicted) == "1 entity not admitted"


def test_error_listing_refuses_measure_only_test_examples() -> None:
    report = StanceReport.__new__(StanceReport)
    report.golden = {"golden_v0-001": golden()}
    report.names = NAMES
    report.test_ids = {"golden_v0-001"}
    report.affiliations = {}
    report.supplement = {}

    with pytest.raises(MeasureOnlySplitError):
        report.errors({"golden_v0-001": row()}, "FP-neg")

    report.test_ids = set()
    listed = report.errors({"golden_v0-001": row()}, "FP-neg")
    assert [(identifier, name) for identifier, name, _, _ in listed] == [
        ("golden_v0-001", "Центр протидії корупції")
    ]


def test_gold_carries_a_linked_persons_criticism_to_the_organization() -> None:
    report = StanceReport.__new__(StanceReport)
    report.golden = {"golden_v0-001": golden()}
    report.names = NAMES
    report.affiliations = {"golden_v0-001": {"Центр протидії корупції"}}
    report.supplement = {"golden_v0-001": {"Служба безпеки України": {"позитивне"}}}

    gold = report.gold("golden_v0-001")
    assert gold["Центр протидії корупції"] == {"відсутнє", "негативне"}
    assert gold["Служба безпеки України"] == {"позитивне"}
