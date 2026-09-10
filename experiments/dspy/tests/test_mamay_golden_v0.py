"""Tests for the Mamay and golden_v0 comparison dataset generator."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from mamay_golden_v0 import (
    completed_example_ids,
    generate_comparisons,
    load_annotations,
)

SOURCE_TEXT = "Петренко заявив."


def golden_annotation(example_id: str = "golden_v0-001") -> dict[str, Any]:
    """Return one complete enough golden record for runner tests."""
    return {
        "example_id": example_id,
        "source": {"post_revision_id": 7, "text": SOURCE_TEXT},
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "mention_span": {"start": 0, "end": 8},
                    "surface_form": "Петренко",
                    "registry_entity_id": "registry-1",
                    "canonical_name": "Петренко",
                    "entity_type": "person",
                    "registry_status": "monitored",
                    "resolution_source": "registry",
                    "subject_role": "primary",
                }
            ],
            "stances": [],
            "claims": [],
            "rhetorical_features": [],
        },
    }


def valid_payload() -> dict[str, Any]:
    """Return a schema- and text-grounded runtime extraction payload."""
    return {
        "schema_version": "extraction_schema_v1",
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "mention_span": {"start": 0, "end": 8},
                    "surface_form": "Петренко",
                    "entity_type": "person",
                    "subject_role": "primary",
                }
            ],
            "stances": [],
            "claims": [],
            "rhetorical_features": [],
        },
    }


class FakeClient:
    """Return configured outcomes without making a network request."""

    def __init__(self, outcomes: list[dict[str, Any] | Exception]) -> None:
        self._outcomes = outcomes

    async def extract(self, post_text: str) -> dict[str, Any]:
        assert post_text == SOURCE_TEXT
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_load_annotations_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "annotations.jsonl"
    record = golden_annotation()
    path.write_text(f"{json.dumps(record)}\n{json.dumps(record)}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate golden example_id"):
        load_annotations(path)


async def test_generator_writes_full_golden_and_valid_mamay_output(tmp_path: Path) -> None:
    output = tmp_path / "comparisons.jsonl"
    annotation = golden_annotation()

    written, failures = await generate_comparisons(
        [annotation], output, FakeClient([valid_payload()]), "test-model", logging.getLogger("test")
    )

    assert (written, failures) == (1, 0)
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["input"] == {
        "example_id": "golden_v0-001",
        "post_revision_id": 7,
        "post_text": SOURCE_TEXT,
    }
    assert row["golden_output"] == annotation["annotations"]
    assert row["mamay_output"] == {"status": "valid", "output": valid_payload()}


async def test_generator_records_failure_and_resumes(tmp_path: Path) -> None:
    output = tmp_path / "comparisons.jsonl"
    annotations = [golden_annotation(), golden_annotation("golden_v0-002")]

    written, failures = await generate_comparisons(
        annotations,
        output,
        FakeClient([RuntimeError("provider details"), valid_payload()]),
        "test-model",
        logging.getLogger("test"),
    )

    assert (written, failures) == (2, 1)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["mamay_output"] == {
        "status": "failed",
        "failure": {
            "kind": "model_request_failed",
            "message": "Model output was unavailable or failed local contract validation.",
        },
    }
    assert completed_example_ids(output) == {"golden_v0-001", "golden_v0-002"}

    written, failures = await generate_comparisons(
        annotations, output, FakeClient([]), "test-model", logging.getLogger("test")
    )

    assert (written, failures) == (0, 0)
