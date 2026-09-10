"""Tests for the text-grounded post-analysis extraction contract."""

from typing import Any

import pytest
from monitoring_common.contracts import (
    ExtractionValidationError,
    load_extraction_schema,
    validate_extraction,
)


def test_runtime_schema_avoids_mamay_unsupported_keywords() -> None:
    """Keep the strict request schema compatible with Mamay's grammar compiler."""
    assert "uniqueItems" not in _schema_keys(load_extraction_schema())


def _schema_keys(value: Any) -> set[str]:
    """Return every JSON Schema keyword used by a nested schema object."""
    if isinstance(value, dict):
        return set(value) | set().union(*(_schema_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_schema_keys(item) for item in value)) if value else set()
    return set()


def test_validator_accepts_grounded_extraction() -> None:
    source_text = "Зеленський заявив, що переговори можливі."
    payload = {
        "schema_version": "extraction_schema_v1",
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "mention_span": {"start": 0, "end": 10},
                    "surface_form": "Зеленський",
                    "entity_type": "person",
                    "subject_role": "primary",
                }
            ],
            "stances": [],
            "claims": [
                {
                    "id": "c1",
                    "normalized_text": "Зеленський заявив, що переговори можливі.",
                    "entity_ids": ["e1"],
                    "evidence_spans": [{"start": 0, "end": len(source_text)}],
                    "attribution": {
                        "source_kind": "named_entity",
                        "source_entity_id": "e1",
                    },
                    "presentation": "editorial",
                    "epistemic_status": "asserted",
                }
            ],
            "rhetorical_features": [],
        },
    }

    validate_extraction(payload, source_text)


def test_validator_rejects_canonical_name() -> None:
    payload = {
        "schema_version": "extraction_schema_v1",
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "mention_span": {"start": 0, "end": 4},
                    "surface_form": "Тест",
                    "canonical_name": "Не дозволено",
                    "entity_type": "person",
                    "subject_role": "primary",
                }
            ],
            "stances": [],
            "claims": [],
            "rhetorical_features": [],
        },
    }

    with pytest.raises(ExtractionValidationError, match="Additional properties"):
        validate_extraction(payload, "Тест")


def test_validator_rejects_unknown_entity_reference() -> None:
    payload = {
        "schema_version": "extraction_schema_v1",
        "annotations": {
            "entities": [],
            "stances": [
                {
                    "entity_id": "e1",
                    "perspective": {
                        "source_kind": "channel_editorial",
                        "source_entity_id": None,
                    },
                    "value": "negative",
                    "evidence_spans": [{"start": 0, "end": 4}],
                }
            ],
            "claims": [],
            "rhetorical_features": [],
        },
    }

    with pytest.raises(ExtractionValidationError, match="unknown entity reference"):
        validate_extraction(payload, "Тест")


def test_validator_rejects_out_of_bounds_span() -> None:
    payload = {
        "schema_version": "extraction_schema_v1",
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "mention_span": {"start": 0, "end": 99},
                    "surface_form": "Тест",
                    "entity_type": "person",
                    "subject_role": "primary",
                }
            ],
            "stances": [],
            "claims": [],
            "rhetorical_features": [],
        },
    }

    with pytest.raises(ExtractionValidationError, match="within source_text"):
        validate_extraction(payload, "Тест")
