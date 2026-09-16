"""Tests for the versioned canonical golden adapter layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from golden_schema import (
    RHETORIC_MAP,
    GoldenV0Adapter,
    GoldenV1Adapter,
    load_golden_jsonl,
    mapping_summary,
)


def legacy_record(
    epistemic: str = "asserted", stance: str = "negative", feature: str = "delegitimization"
) -> dict[str, Any]:
    """Return a compact valid-enough v0 sample with one claim-target pair."""
    return {
        "schema_version": "annotation_schema_v1",
        "example_id": "golden_v0-001",
        "source": {"text": "Target is bad."},
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "registry_entity_id": "local-1",
                    "canonical_name": "Target",
                    "registry_status": "candidate",
                }
            ],
            "claims": [
                {
                    "id": "c1",
                    "normalized_text": "Target is bad.",
                    "entity_ids": ["e1"],
                    "evidence_spans": [{"start": 0, "end": 14}],
                    "attribution": {"source_kind": "channel_editorial"},
                    "epistemic_status": epistemic,
                }
            ],
            "stances": [
                {
                    "entity_id": "e1",
                    "perspective": {"source_kind": "channel_editorial"},
                    "value": stance,
                    "evidence_spans": [{"start": 0, "end": 14}],
                }
            ],
            "rhetorical_features": [
                {
                    "feature_type": feature,
                    "target_entity_id": "e1",
                    "target_claim_id": "c1",
                    "evidence_span": {"start": 0, "end": 14},
                }
            ],
        },
    }


@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [
        ("asserted", "ствердження"),
        ("alleged", "невпевнене"),
        ("hypothetical", "невпевнене"),
        ("questioned", "питання"),
    ],
)
def test_maps_all_supported_legacy_epistemic_values(legacy: str, canonical: str) -> None:
    result = GoldenV0Adapter().convert(legacy_record(epistemic=legacy))
    assert result.claims[0].epistemic_status == canonical


@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [("negative", "негативне"), ("positive", "позитивне"), ("neutral", "відсутнє")],
)
def test_maps_all_supported_legacy_stance_values(legacy: str, canonical: str) -> None:
    result = GoldenV0Adapter().convert(legacy_record(stance=legacy))
    assert result.classifications[0].stance == canonical


def test_insufficient_context_is_unscorable_not_neutral() -> None:
    canonical = GoldenV0Adapter().convert(legacy_record(stance="insufficient_context"))
    assert canonical.classifications[0].stance is None
    assert any(item["kind"] == "unresolved_legacy_stance" for item in canonical.mapping_warnings)


@pytest.mark.parametrize(("field", "legacy"), [("stance", "mixed"), ("epistemic", "denied")])
def test_unsupported_legacy_semantics_remain_unresolved(field: str, legacy: str) -> None:
    kwargs = {field: legacy}
    canonical = GoldenV0Adapter().convert(legacy_record(**kwargs))
    if field == "stance":
        assert canonical.classifications[0].stance is None
        warning_kind = "unresolved_legacy_stance"
    else:
        assert canonical.claims[0].epistemic_status is None
        warning_kind = "unresolved_legacy_epistemic"
    assert any(
        warning["kind"] == warning_kind
        and warning["legacy_value"] == legacy
        and warning["resolution"] == "unresolved_legacy"
        for warning in canonical.mapping_warnings
    )


@pytest.mark.parametrize("legacy", sorted(RHETORIC_MAP))
def test_maps_every_supported_legacy_rhetoric_label(legacy: str) -> None:
    canonical = GoldenV0Adapter().convert(legacy_record(feature=legacy))
    assert canonical.classifications[0].rhetoric == [RHETORIC_MAP[legacy]]


@pytest.mark.parametrize("legacy", ["grant_discrediting", "call_for_punishment"])
def test_preserves_unmapped_legacy_rhetoric_for_reporting(legacy: str) -> None:
    canonical = GoldenV0Adapter().convert(legacy_record(feature=legacy))
    assert canonical.classifications[0].rhetoric == []
    assert canonical.unmapped_legacy_labels == [
        {
            "kind": "unmapped_legacy_rhetoric",
            "claim_id": "c1",
            "entity_id": "e1",
            "legacy_feature": legacy,
            "mapped_feature": None,
        }
    ]


def test_ambiguous_unlinked_rhetoric_is_not_attached() -> None:
    record = legacy_record()
    record["annotations"]["claims"].append(
        {
            **record["annotations"]["claims"][0],
            "id": "c2",
            "evidence_spans": [{"start": 0, "end": 14}],
        }
    )
    record["annotations"]["rhetorical_features"][0].pop("target_claim_id")
    canonical = GoldenV0Adapter().convert(record)
    assert all(not item.rhetoric for item in canonical.classifications)
    assert canonical.ambiguous_mappings


def test_v1_rejects_rhetoric_on_non_negative_stance() -> None:
    record = {
        "schema_version": "golden_v1",
        "example_id": "golden_v1-001",
        "source": {"text": "Target text"},
        "entities": [
            {
                "id": "e1",
                "registry_entity_id": 1,
                "canonical_name": "Target",
                "monitored": True,
            }
        ],
        "claims": [
            {
                "id": "c1",
                "normalized_text": "Target text",
                "entity_ids": ["e1"],
                "evidence_text": "Target text",
                "attribution": {
                    "source_kind": "channel_editorial",
                    "source_entity_id": None,
                },
                "epistemic_status": "ствердження",
            }
        ],
        "classifications": [
            {
                "claim_id": "c1",
                "entity_id": "e1",
                "stance": "позитивне",
                "rhetoric": ["делегітимізація"],
            }
        ],
    }
    with pytest.raises(ValueError, match="non-negative"):
        GoldenV1Adapter(Path("experiments/datasets/golden_v1/annotation_schema_v1.json")).convert(
            record
        )


def test_all_active_annotations_load_through_the_legacy_adapter() -> None:
    records = load_golden_jsonl(Path("experiments/datasets/golden_v0/data/annotations.jsonl"))
    assert len(records) == 100
    assert all(record.original_schema_version == "annotation_schema_v1" for record in records)
    summary = mapping_summary(records)
    assert summary["mapped_claims"] == 785
    assert summary["generated_classifications"] == 1579
