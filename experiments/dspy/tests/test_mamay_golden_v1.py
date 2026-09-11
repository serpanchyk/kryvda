"""Tests for the reduced Mamay v2 comparison experiment."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from mamay_golden_v1 import (
    ExtractionValidationError,
    completed_example_ids,
    generate_comparisons,
    project_golden,
    validate_extraction,
)

SOURCE_TEXT = "Петренко заявив, що справа закрита."


def golden_annotation(example_id: str = "golden_v0-001") -> dict[str, Any]:
    """Return one golden record with named attribution and rhetoric."""
    return {
        "example_id": example_id,
        "source": {"post_revision_id": 7, "text": SOURCE_TEXT},
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "mention_span": {"start": 0, "end": 8},
                    "surface_form": "Петренко",
                    "entity_type": "person",
                    "subject_role": "primary",
                    "registry_entity_id": "registry-1",
                    "canonical_name": "Петренко",
                    "registry_status": "monitored",
                    "resolution_source": "registry",
                }
            ],
            "stances": [],
            "claims": [
                {
                    "id": "c1",
                    "normalized_text": "Петренко заявив, що справа закрита.",
                    "entity_ids": ["e1"],
                    "evidence_spans": [{"start": 0, "end": len(SOURCE_TEXT)}],
                    "attribution": {"source_kind": "named_entity", "source_entity_id": "e1"},
                    "presentation": "reported",
                    "epistemic_status": "asserted",
                }
            ],
            "rhetorical_features": [
                {
                    "feature_type": "delegitimization",
                    "evidence_span": {"start": 0, "end": 8},
                    "target_entity_id": "e1",
                    "target_claim_id": "c1",
                    "perspective": {"source_kind": "named_entity", "source_entity_id": "e1"},
                }
            ],
        },
    }


def valid_payload() -> dict[str, Any]:
    """Return a schema-valid, text-grounded v2 response."""
    return {
        "schema_version": "mamay_extraction_schema_v2",
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "surface_form": "Петренко",
                    "entity_type": "person",
                    "subject_role": "primary",
                }
            ],
            "stances": [],
            "claims": [
                {
                    "id": "c1",
                    "normalized_text": "Петренко заявив, що справа закрита.",
                    "entity_ids": ["e1"],
                    "evidence_text": SOURCE_TEXT,
                    "attribution": {
                        "source_kind": "named_entity",
                        "source_surface_form": "Петренко",
                    },
                    "presentation": "reported",
                    "epistemic_status": "asserted",
                    "rhetorical_features": [],
                }
            ],
        },
    }


class FakeClient:
    """Return configured outcomes without model requests."""

    def __init__(self, outcomes: list[dict[str, Any] | Exception]) -> None:
        self._outcomes = outcomes

    async def extract(self, post_text: str) -> dict[str, Any]:
        """Return the next configured outcome."""
        assert post_text == SOURCE_TEXT
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_projection_drops_downstream_fields_and_nests_rhetoric() -> None:
    """Golden v0 is projected to the exact Mamay-facing v2 shape."""
    projection = project_golden(golden_annotation())

    entity = projection["annotations"]["entities"][0]
    assert set(entity) == {"id", "surface_form", "entity_type", "subject_role"}
    claim = projection["annotations"]["claims"][0]
    assert claim["evidence_text"] == SOURCE_TEXT
    assert claim["attribution"]["source_surface_form"] == "Петренко"
    assert claim["rhetorical_features"] == ["delegitimization"]


def test_validator_rejects_unanchored_text_and_nonsequential_ids() -> None:
    """Model anchors and local IDs remain deterministic without offsets."""
    payload = valid_payload()
    payload["annotations"]["entities"][0]["surface_form"] = "Відсутній"
    with pytest.raises(ExtractionValidationError, match="must occur exactly"):
        validate_extraction(payload, SOURCE_TEXT)

    payload = valid_payload()
    payload["annotations"]["entities"][0]["id"] = "e2"
    with pytest.raises(ExtractionValidationError, match="sequential"):
        validate_extraction(payload, SOURCE_TEXT)


async def test_generator_writes_projection_and_preserves_invalid_payload(tmp_path: Path) -> None:
    """Parsed invalid output remains reviewable while projection stays auditable."""
    output = tmp_path / "comparisons.jsonl"
    invalid = valid_payload()
    invalid["annotations"]["claims"][0]["evidence_text"] = "немає в тексті"

    written, failures = await generate_comparisons(
        [golden_annotation()],
        output,
        FakeClient([invalid]),
        "test-model",
        logging.getLogger("test"),
    )

    assert (written, failures) == (1, 1)
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["golden_v2_projection"]["schema_version"] == "mamay_extraction_schema_v2"
    assert row["mamay_output"]["status"] == "invalid"
    assert completed_example_ids(output) == {"golden_v0-001"}


async def test_generator_resumes_completed_rows(tmp_path: Path) -> None:
    """A resumed run never requests a persisted example twice."""
    output = tmp_path / "comparisons.jsonl"
    annotation = golden_annotation()
    await generate_comparisons(
        [annotation], output, FakeClient([valid_payload()]), "test-model", logging.getLogger("test")
    )

    written, failures = await generate_comparisons(
        [annotation], output, FakeClient([]), "test-model", logging.getLogger("test")
    )
    assert (written, failures) == (0, 0)
