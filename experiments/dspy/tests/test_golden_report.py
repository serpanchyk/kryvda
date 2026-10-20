"""Tests for golden benchmark partitioning."""

from __future__ import annotations

import json
from pathlib import Path

from golden_report import (
    EvaluationItem,
    benchmark_report,
    extension_example_ids,
    heldout_example_ids,
)
from golden_schema import CanonicalGolden
from jev_golden_v1 import select_examples


def item(example_id: str) -> EvaluationItem:
    golden = CanonicalGolden(example_id, "text", [], [], [], "annotation_schema_v1")
    return EvaluationItem(golden, None, degraded=True)


def test_extension_examples_never_join_diagnostic45(tmp_path: Path) -> None:
    annotations = tmp_path / "annotations.jsonl"
    assert extension_example_ids(annotations) == set()
    rows = [
        {"example_id": "golden_v0-001", "partition": "pilot100"},
        {"example_id": "golden_v0-266", "partition": "extension400"},
    ]
    annotations.with_name("annotation_provenance.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    extension = extension_example_ids(annotations)
    assert extension == {"golden_v0-266"}
    items = [item("golden_v0-001"), item("golden_v0-002"), item("golden_v0-266")]
    report = benchmark_report(items, {"golden_v0-001"}, extension)
    assert report["all100"]["examples"] == 2
    assert report["diagnostic45"]["examples"] == 1
    assert report["extension400"]["examples"] == 1
    assert report["all"]["examples"] == 3
    assert "extension400" not in benchmark_report(items[:2], {"golden_v0-001"})


def test_select_examples_isolates_extension_partition() -> None:
    records = [{"example_id": name} for name in ("a", "b", "c")]
    assert select_examples(records, "diagnostic45", {"a"}, {"c"}) == [{"example_id": "b"}]
    assert select_examples(records, "extension400", {"a"}, {"c"}) == [{"example_id": "c"}]


def test_measure_only_test_split_is_read_and_reported_separately(tmp_path: Path) -> None:
    annotations = tmp_path / "data" / "annotations.jsonl"
    annotations.parent.mkdir()
    assert heldout_example_ids(annotations) == set()
    (tmp_path / "test_split.json").write_text(
        json.dumps({"example_ids": ["golden_v0-266"]}), encoding="utf-8"
    )
    test_ids = heldout_example_ids(annotations)
    items = [item("golden_v0-001"), item("golden_v0-266"), item("golden_v0-267")]

    report = benchmark_report(
        items, {"golden_v0-001"}, {"golden_v0-266", "golden_v0-267"}, test_ids
    )

    assert test_ids == {"golden_v0-266"}
    assert report["test"]["examples"] == 1
    assert report["dev"]["examples"] == 2
    assert "test" not in benchmark_report(items, {"golden_v0-001"})


def test_repository_test_split_holds_only_examples_added_after_prompt_work() -> None:
    split = json.loads(Path("experiments/datasets/golden_v0/test_split.json").read_text())
    identifiers = split["example_ids"]

    assert split["split_version"] == "golden_v0_test_v2"
    assert len(identifiers) == len(set(identifiers)) == 249
    assert all(int(name.removeprefix("golden_v0-")) >= 666 for name in identifiers)
