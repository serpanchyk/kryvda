"""Tests for the positive-context re-review of neutral golden_v0 stance records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from golden_v0_extension_import import materialize
from golden_v0_stance_relabel import LOG_FILE, apply, export, load_decisions, review_items

TEXT = "НАБУ знову провалилося."
POST = {
    "post_revision_id": 7,
    "raw_post_id": 7,
    "channel_id": 1,
    "channel_reference": "example",
    "telegram_message_id": 7,
    "published_at": "2026-09-08T12:00:00+00:00",
    "text": TEXT,
}

REGISTRY = [
    {
        "id": "local-1",
        "canonical_name": "Національне антикорупційне бюро України",
        "aliases": ["НАБУ"],
        "entity_type": "state_institution",
        "status": "candidate",
    }
]


def anchor(stance: str = "negative") -> dict[str, Any]:
    editorial = {"source_kind": "channel_editorial"}
    return {
        "selection": {"facets": ["НАБУ"], "reason": "Пост про НАБУ."},
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "surface_form": "НАБУ",
                    "canonical_name": "Національне антикорупційне бюро України",
                    "entity_type": "state_institution",
                    "subject_role": "primary",
                }
            ],
            "stances": [
                {"entity_id": "e1", "perspective": editorial, "value": stance, "evidence": [TEXT]}
            ],
            "claims": [
                {
                    "id": "c1",
                    "normalized_text": "Канал стверджує, що НАБУ знову провалилося.",
                    "entity_ids": ["e1"],
                    "evidence": [TEXT],
                    "attribution": editorial,
                    "presentation": "editorial",
                    "epistemic_status": "asserted",
                }
            ],
            "rhetorical_features": [],
        },
    }


def neutral_record() -> dict[str, Any]:
    record = materialize(anchor("neutral"), POST, "golden_v0-002")
    record["annotations"]["entities"][0]["registry_entity_id"] = "local-1"
    return record


def test_review_items_cover_only_neutral_records_with_overlapping_claims() -> None:
    items = review_items(neutral_record())

    assert items == [
        {
            "item_id": "golden_v0-002:s0",
            "entity": "Національне антикорупційне бюро України",
            "perspective": "channel_editorial",
            "perspective_entity": None,
            "evidence": ["НАБУ знову провалилося."],
            "claims": ["Канал стверджує, що НАБУ знову провалилося."],
        }
    ]
    assert review_items(materialize(anchor(), POST, "golden_v0-003")) == []


def test_export_and_decisions_round_trip(tmp_path: Path) -> None:
    assert export([neutral_record()], tmp_path, 2) == [1]
    batch = tmp_path / "batches" / "r01"
    (batch / "out.json").write_text(json.dumps({}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        load_decisions(tmp_path)
    (batch / "out.json").write_text(
        json.dumps({"golden_v0-002:s0": {"value": "positive", "reason": "успіх"}}),
        encoding="utf-8",
    )
    assert load_decisions(tmp_path) == {
        "golden_v0-002:s0": {"value": "positive", "reason": "успіх"}
    }


def test_apply_saves_positive_decisions_through_the_editor(tmp_path: Path) -> None:
    (tmp_path / "editor.json").write_text(
        json.dumps(
            {
                "records": {"7": {"version": 1, "status": "completed", "record": neutral_record()}},
                "registry": REGISTRY,
            }
        ),
        encoding="utf-8",
    )
    decisions = {"golden_v0-002:s0": {"value": "positive", "reason": "успіх"}}

    assert apply(tmp_path, decisions, "2026-10-21T00:00:00+00:00") == 1

    exported = json.loads((tmp_path / "annotations.jsonl").read_text(encoding="utf-8"))
    assert exported["annotations"]["stances"][0]["value"] == "positive"
    log = json.loads((tmp_path / LOG_FILE).read_text(encoding="utf-8"))
    assert (log["item_id"], log["to"]) == ("golden_v0-002:s0", "positive")
    assert apply(tmp_path, decisions, "2026-10-21T00:00:00+00:00") == 1
    state = json.loads((tmp_path / "editor.json").read_text(encoding="utf-8"))
    assert state["records"]["7"]["version"] == 2
    state["records"]["7"]["record"]["annotations"]["stances"][0]["value"] = "negative"
    (tmp_path / "editor.json").write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ValueError, match="no longer neutral"):
        apply(tmp_path, decisions, "2026-10-21T00:00:00+00:00")
