"""Tests for quote-anchored golden_v0 extension tooling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from golden_schema import GoldenV0Adapter
from golden_v0_anchor import AnchorError, check_directory, locate, to_anchor, to_payload
from golden_v0_extension import normalized_text, select_posts, write_batches
from golden_v0_extension_import import (
    agreement,
    import_batches,
    materialize,
    normalize_entities,
    renormalize_imported,
)

TEXT = "НАБУ знову провалилося. Канал вважає, що НАБУ працює на грантодавців."
POST = {
    "post_revision_id": 7,
    "raw_post_id": 7,
    "channel_id": 1,
    "channel_reference": "example",
    "telegram_message_id": 7,
    "published_at": "2026-09-08T12:00:00+00:00",
    "text": TEXT,
}


def anchor(stance: str = "negative") -> dict[str, Any]:
    editorial = {"source_kind": "channel_editorial"}
    return {
        "selection": {"facets": ["НАБУ"], "reason": "Канал дискредитує НАБУ."},
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
                {
                    "entity_id": "e1",
                    "perspective": editorial,
                    "value": stance,
                    "evidence": ["НАБУ знову провалилося."],
                }
            ],
            "claims": [
                {
                    "id": "c1",
                    "normalized_text": "Канал стверджує, що НАБУ знову провалилося.",
                    "entity_ids": ["e1"],
                    "evidence": ["НАБУ знову провалилося."],
                    "attribution": editorial,
                    "presentation": "editorial",
                    "epistemic_status": "asserted",
                }
            ],
            "rhetorical_features": [
                {
                    "feature_type": "delegitimization",
                    "evidence": "знову провалилося",
                    "target_entity_id": "e1",
                    "target_claim_id": "c1",
                    "perspective": editorial,
                }
            ],
        },
    }


def test_locate_resolves_later_occurrence_and_rejects_missing_quote() -> None:
    assert locate(TEXT, {"text": "НАБУ", "occurrence": 2}, "x") == {"start": 41, "end": 45}
    with pytest.raises(AnchorError, match="not found"):
        locate(TEXT, "СБУ", "x")
    with pytest.raises(AnchorError, match="non-empty"):
        locate(TEXT, "", "x")


def test_anchor_round_trip_preserves_spans() -> None:
    payload = to_payload(anchor(), TEXT)
    record = materialize(anchor(), POST, "golden_v0-001")
    assert payload["annotations"]["claims"][0]["evidence_spans"] == [{"start": 0, "end": 23}]
    assert to_payload(to_anchor(record), TEXT)["annotations"] == {
        **payload["annotations"],
        "entities": [
            {**entity, "canonical_name": "Національне антикорупційне бюро України"}
            for entity in payload["annotations"]["entities"]
        ],
    }


def test_check_directory_reports_errors_warnings_and_missing(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    second = {**POST, "post_revision_id": 8}
    (tmp_path / "posts.json").write_text(json.dumps([POST, second]), encoding="utf-8")
    broken = anchor()
    broken["annotations"]["stances"] = []
    broken["annotations"]["claims"][0]["attribution"] = {"source_kind": "named_entity"}
    (tmp_path / "out" / "7.json").write_text(json.dumps(broken), encoding="utf-8")
    lines = check_directory(tmp_path)
    assert lines[0].startswith("7: FAIL")
    assert any("requires source_entity_id" in line for line in lines)
    assert lines[-1] == "8: MISSING"
    (tmp_path / "out" / "7.json").write_text(json.dumps(anchor()), encoding="utf-8")
    assert check_directory(tmp_path)[0] == "7: OK (0 errors, 0 warnings)"


def test_selection_deduplicates_filters_and_prefers_core_posts() -> None:
    rows = [
        {**POST, "raw_post_id": index, "post_revision_id": index, "text": text}
        for index, text in enumerate(
            [
                "НАБУ провалило розслідування, — пише канал. " * 4,
                "НАБУ провалило розслідування, — пише канал. " * 4,
                "ЗСУ уразили склад; Генштаб повідомив подробиці операції. " * 3,
                "Новина без жодного актора моніторингу, лише погода й дощ. " * 3,
                "коротко про НАБУ",
            ],
            start=1,
        )
    ]

    def match(text: str) -> list[str]:
        return [name for name in ("НАБУ", "ЗСУ") if name in text]

    chosen = select_posts(rows, match, {"НАБУ"}, set(), set(), target=2)
    assert sorted(post["raw_post_id"] for post in chosen) == [1, 3]
    assert {post["core"] for post in chosen} == {True, False}
    excluded = select_posts(rows, match, {"НАБУ"}, {1}, {normalized_text(rows[2]["text"])}, 2)
    assert [post["raw_post_id"] for post in excluded] == [2]


def test_agreement_scores_entities_negative_stance_and_rhetoric() -> None:
    adapter = GoldenV0Adapter()
    reference = adapter.convert(materialize(anchor(), POST, "golden_v0-001"))
    neutral = anchor("neutral")
    neutral["annotations"]["rhetorical_features"] = []
    candidate = adapter.convert(materialize(neutral, POST, "golden_v0-001"))
    same = agreement([(reference, reference)])
    assert same["negative_target"]["f1"] == 1.0
    assert same["rhetoric_labels"]["f1"] == 1.0
    different = agreement([(reference, candidate)])
    assert different["target_entities"]["f1"] == 1.0
    assert different["negative_target"]["recall"] == 0.0
    assert different["shared_entity_stance_set_exact"] == 0.0


def test_import_completes_records_and_records_provenance(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    legacy = materialize(anchor(), {**POST, "post_revision_id": 1}, "golden_v0-001")
    (data / "editor.json").write_text(
        json.dumps(
            {
                "records": {"1": {"version": 2, "status": "completed", "record": legacy}},
                "registry": [],
            }
        ),
        encoding="utf-8",
    )
    (data / "annotations.jsonl").write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    batch = tmp_path / "b01"
    write_batches([POST], tmp_path, "b")
    (batch / "out" / "7.json").write_text(json.dumps(anchor()), encoding="utf-8")
    assert import_batches([batch], data, "2026-10-10T00:00:00+00:00") == ["golden_v0-002"]
    records = [json.loads(line) for line in (data / "annotations.jsonl").read_text().splitlines()]
    assert [record["example_id"] for record in records] == ["golden_v0-001", "golden_v0-002"]
    assert records[1]["annotations"]["entities"][0]["registry_entity_id"] == "local-1"
    provenance = [
        json.loads(line) for line in (data / "annotation_provenance.jsonl").read_text().splitlines()
    ]
    assert [row["partition"] for row in provenance] == ["pilot100", "extension400"]
    with pytest.raises(ValueError, match="already in the editor"):
        import_batches([batch], data, "2026-10-10T00:00:00+00:00")


def test_normalize_entities_merges_variants_and_types() -> None:
    first, second, third = anchor(), anchor(), anchor()
    first["annotations"]["entities"][0].update(canonical_name="Росія", entity_type="organization")
    second["annotations"]["entities"][0].update(canonical_name="Новий Актор", entity_type="person")
    third["annotations"]["entities"][0].update(
        canonical_name="Новий Актор", entity_type="political_actor"
    )
    extra = anchor()
    extra["annotations"]["entities"][0].update(canonical_name="Новий Актор", entity_type="person")
    zelensky = anchor()
    zelensky["annotations"]["entities"][0].update(
        canonical_name="Володимир Зеленський", entity_type="political_actor"
    )
    registry = [
        {"canonical_name": "Російська Федерація", "entity_type": "political_actor"},
        {"canonical_name": "Володимир Зеленський", "entity_type": "political_actor"},
        {"canonical_name": "Володимир Зеленський", "entity_type": "person"},
    ]
    normalize_entities([first, second, third, extra, zelensky], registry)
    assert first["annotations"]["entities"][0]["canonical_name"] == "Російська Федерація"
    assert first["annotations"]["entities"][0]["entity_type"] == "political_actor"
    assert {a["annotations"]["entities"][0]["entity_type"] for a in (second, third)} == {"person"}
    assert zelensky["annotations"]["entities"][0]["entity_type"] == "person"


def test_renormalize_imported_re_resolves_variant_names(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    variant = anchor()
    variant["annotations"]["entities"][0].update(
        canonical_name="Росія", entity_type="political_actor"
    )
    record = materialize(variant, POST, "golden_v0-002")
    record["annotations"]["entities"][0]["registry_entity_id"] = "local-1"
    registry = [
        {
            "id": "local-1",
            "canonical_name": "Росія",
            "aliases": ["НАБУ"],
            "entity_type": "political_actor",
            "status": "candidate",
        },
        {
            "id": "local-2",
            "canonical_name": "Російська Федерація",
            "aliases": ["РФ"],
            "entity_type": "political_actor",
            "status": "candidate",
        },
    ]
    (data / "editor.json").write_text(
        json.dumps(
            {
                "records": {"7": {"version": 1, "status": "completed", "record": record}},
                "registry": registry,
            }
        ),
        encoding="utf-8",
    )
    assert renormalize_imported(data) == []
    (data / "annotation_provenance.jsonl").write_text(
        json.dumps({"example_id": "golden_v0-002", "partition": "extension400"}) + "\n",
        encoding="utf-8",
    )
    assert renormalize_imported(data) == ["golden_v0-002"]
    state = json.loads((data / "editor.json").read_text(encoding="utf-8"))
    entity = state["records"]["7"]["record"]["annotations"]["entities"][0]
    assert (entity["canonical_name"], entity["registry_entity_id"]) == (
        "Російська Федерація",
        "local-2",
    )
