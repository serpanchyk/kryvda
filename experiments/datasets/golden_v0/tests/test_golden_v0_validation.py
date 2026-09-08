"""Tests for the golden_v0 annotation validator."""

from __future__ import annotations

import json
from pathlib import Path

from golden_v0_validation import validate_dataset


def test_validator_accepts_quote_with_attributed_stance(tmp_path: Path) -> None:
    text = "Іван сказав: «Організація Y краде гранти»."
    record = {
        "example_id": "golden_v0-001",
        "schema_version": "annotation_schema_v1",
        "source": {
            "channel_id": 1,
            "channel_reference": "example",
            "raw_post_id": 1,
            "post_revision_id": 1,
            "telegram_message_id": 1,
            "published_at": "2026-09-08T12:00:00+00:00",
            "text": text,
        },
        "selection": {
            "facets": ["quotation", "corruption_accusation"],
            "reason": "Covers attributed negative stance.",
            "is_keyword_false_positive": False,
        },
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "mention_span": {"start": 0, "end": 4},
                    "surface_form": "Іван",
                    "registry_entity_id": "entity-ivan",
                    "canonical_name": "Іван",
                    "entity_type": "person",
                    "registry_status": "candidate",
                    "resolution_source": "annotator_knowledge",
                    "subject_role": "secondary",
                },
                {
                    "id": "e2",
                    "mention_span": {"start": 14, "end": 27},
                    "surface_form": "Організація Y",
                    "registry_entity_id": "entity-organization-y",
                    "canonical_name": "Організація Y",
                    "entity_type": "organization",
                    "registry_status": "monitored",
                    "resolution_source": "registry",
                    "subject_role": "primary",
                },
            ],
            "stances": [
                {
                    "entity_id": "e2",
                    "perspective": {"source_kind": "named_entity", "source_entity_id": "e1"},
                    "value": "negative",
                    "evidence_spans": [{"start": 28, "end": 40}],
                }
            ],
            "claims": [
                {
                    "id": "c1",
                    "normalized_text": "Організація Y краде гранти.",
                    "entity_ids": ["e2"],
                    "evidence_spans": [{"start": 14, "end": 40}],
                    "attribution": {"source_kind": "named_entity", "source_entity_id": "e1"},
                    "presentation": "direct_quote",
                    "epistemic_status": "asserted",
                }
            ],
            "rhetorical_features": [
                {
                    "feature_type": "corruption_accusation",
                    "evidence_span": {"start": 28, "end": 40},
                    "target_entity_id": "e2",
                    "perspective": {"source_kind": "named_entity", "source_entity_id": "e1"},
                }
            ],
        },
    }
    path = tmp_path / "annotations.jsonl"
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

    assert validate_dataset(path) == []


def test_validator_reports_invalid_surface_span_and_reference(tmp_path: Path) -> None:
    record = {
        "example_id": "golden_v0-002",
        "schema_version": "annotation_schema_v1",
        "source": {
            "channel_id": 1,
            "channel_reference": "example",
            "raw_post_id": 2,
            "post_revision_id": 2,
            "telegram_message_id": 2,
            "published_at": "2026-09-08T12:00:00+00:00",
            "text": "Тест",
        },
        "selection": {
            "facets": ["edge_case"],
            "reason": "Validator test.",
            "is_keyword_false_positive": False,
        },
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "mention_span": {"start": 0, "end": 2},
                    "surface_form": "Інше",
                    "registry_entity_id": None,
                    "canonical_name": "Тест",
                    "entity_type": "person",
                    "registry_status": "candidate",
                    "resolution_source": "registry",
                    "subject_role": "primary",
                }
            ],
            "stances": [],
            "claims": [],
            "rhetorical_features": [
                {
                    "feature_type": "ridicule",
                    "evidence_span": {"start": 0, "end": 4},
                    "target_entity_id": "missing",
                    "perspective": {"source_kind": "channel_editorial"},
                }
            ],
        },
    }
    path = tmp_path / "annotations.jsonl"
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

    errors = validate_dataset(path)

    assert any("surface_form does not match" in error for error in errors)
    assert any("feature target entity does not reference" in error for error in errors)
