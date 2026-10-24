"""Tests for the gold supplement of registry entities the annotators had skipped."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from golden_v0_supplement import collect


def write_batch(root: Path, answer: dict[str, object]) -> None:
    batch = root / "work" / "batches" / "s01"
    batch.mkdir(parents=True, exist_ok=True)
    items = [
        {
            "example_id": "golden_v0-001",
            "text": "Поліція мовчить.",
            "entities": ["Національна поліція України", "Голос"],
        }
    ]
    (batch / "items.json").write_text(json.dumps(items), "utf-8")
    (batch / "out.json").write_text(json.dumps({"golden_v0-001": answer}), "utf-8")


def test_collect_keeps_referenced_entities_with_their_stances(tmp_path: Path) -> None:
    police = {"referenced": True, "negative": True, "positive": False, "reason": "мовчить"}
    voice = {"referenced": False, "negative": False, "positive": False, "reason": "слово"}
    write_batch(tmp_path, {"Національна поліція України": police, "Голос": voice})

    assert collect(tmp_path / "work", tmp_path) == 1
    row = json.loads((tmp_path / "supplement_stances.jsonl").read_text(encoding="utf-8"))
    assert (row["entity"], row["stances"]) == ("Національна поліція України", ["негативне"])
    write_batch(tmp_path, {"Голос": voice})
    with pytest.raises(ValueError, match="missing"):
        collect(tmp_path / "work", tmp_path)
