"""Tests for person-to-organization links in golden_v0."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from golden_v0_affiliations import collect, review_post

ALIASES = [
    {
        "entity_id": 1,
        "canonical_name": "Віталій Шабунін",
        "coarse_type": "person",
        "monitored": True,
        "alias": "Шабунін",
    },
    {
        "entity_id": 2,
        "canonical_name": "Центр протидії корупції",
        "coarse_type": "organization",
        "monitored": True,
        "alias": "ЦПК",
    },
]


def record(value: str = "negative") -> dict[str, Any]:
    return {
        "example_id": "golden_v0-001",
        "source": {"text": "Голова ЦПК Шабунін бреше."},
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "entity_type": "person",
                    "canonical_name": "Віталій Шабунін",
                    "surface_form": "Шабунін",
                }
            ],
            "stances": [{"entity_id": "e1", "value": value}],
        },
    }


def test_review_post_offers_criticised_people_and_registry_organizations() -> None:
    assert review_post(record(), ALIASES) == {
        "example_id": "golden_v0-001",
        "text": "Голова ЦПК Шабунін бреше.",
        "people": [{"entity_id": "e1", "name": "Віталій Шабунін"}],
        "organizations": ["Центр протидії корупції"],
    }
    assert review_post(record("neutral"), ALIASES) is None


def test_collect_keeps_linked_people_and_rejects_unknown_organizations(tmp_path: Path) -> None:
    batch = tmp_path / "work" / "batches" / "a01"
    batch.mkdir(parents=True)
    (batch / "items.json").write_text(json.dumps([review_post(record(), ALIASES)]), "utf-8")
    answer = {
        "golden_v0-001": {"e1": {"organizations": ["Центр протидії корупції"], "reason": "голова"}}
    }
    (batch / "out.json").write_text(json.dumps(answer), "utf-8")

    assert collect(tmp_path / "work", tmp_path) == 1
    link = json.loads((tmp_path / "affiliations.jsonl").read_text(encoding="utf-8"))
    assert (link["entity_id"], link["organizations"]) == ("e1", ["Центр протидії корупції"])
    answer["golden_v0-001"]["e1"]["organizations"] = ["НАБУ"]
    (batch / "out.json").write_text(json.dumps(answer), "utf-8")
    with pytest.raises(ValueError, match="unknown organizations"):
        collect(tmp_path / "work", tmp_path)
