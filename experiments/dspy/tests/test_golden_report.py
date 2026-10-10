"""Tests for golden benchmark partitioning."""

from __future__ import annotations

import json
from pathlib import Path

from golden_report import EvaluationItem, benchmark_report, extension_example_ids
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
