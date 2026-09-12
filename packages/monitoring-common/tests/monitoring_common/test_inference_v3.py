"""Contract tests for the focused inference-v3 passes."""

import pytest
from monitoring_common.contracts import (
    InferenceValidationError,
    alias_occurs,
    normalize_match_text,
    parse_json_object,
    validate_pass,
    validation_errors,
)

TEXT = "Віталій Шабунін заявив, що ЦПК працює."
ENTITIES = [
    {
        "id": "e1",
        "mentions": ["Віталій Шабунін"],
        "canonical_name": "Віталій Шабунін",
        "monitored": True,
    },
    {
        "id": "e2",
        "mentions": ["ЦПК"],
        "canonical_name": "Центр протидії корупції",
        "monitored": False,
    },
]


def test_alias_matching_is_casefolded_literal_and_boundary_aware() -> None:
    assert alias_occurs("Заява ЦПК.", "цпк")
    assert alias_occurs("Про Anti-Corruption Action Centre!", "Anti-Corruption Action Centre")
    assert not alias_occurs("слово накопичено", "ОП")
    assert not alias_occurs("Шабуніна згадали", "Шабунін")
    assert normalize_match_text("  Дар’я   КАЛЕНЮК ") == "дар’я каленюк"


def test_entity_validation_accepts_exact_groups_and_rejects_grounding() -> None:
    validate_pass(
        "entities",
        {"entities": [{"mentions": ["Віталій Шабунін"]}, {"mentions": ["ЦПК"]}]},
        TEXT,
    )
    with pytest.raises(InferenceValidationError) as captured:
        validate_pass("entities", {"entities": [{"mentions": ["Шабуніна"]}]}, TEXT)
    assert validation_errors(captured.value)[0]["kind"] == "grounding_failure"


def test_entity_validation_rejects_duplicate_mentions_across_groups() -> None:
    with pytest.raises(InferenceValidationError, match="multiple entity groups"):
        validate_pass(
            "entities",
            {"entities": [{"mentions": ["ЦПК"]}, {"mentions": ["ЦПК"]}]},
            TEXT,
        )


def test_runtime_schemas_avoid_unsupported_unique_items() -> None:
    from monitoring_common.contracts import load_inference_schema

    for pass_name in ("entities", "claims", "classification"):
        assert "uniqueItems" not in str(load_inference_schema(pass_name))


def test_claim_validation_enforces_grounding_scope_and_attribution() -> None:
    payload = {
        "claims": [
            {
                "normalized_text": "Віталій Шабунін заявив, що ЦПК працює.",
                "entity_ids": ["e1", "e2"],
                "evidence_text": TEXT,
                "attribution": {"source_kind": "named_entity", "source_entity_id": "e1"},
                "epistemic_status": "ствердження",
                "presentation": "не_цитата",
            }
        ]
    }
    validate_pass("claims", payload, TEXT, ENTITIES)

    payload["claims"][0]["entity_ids"] = ["e1", "e1"]
    with pytest.raises(InferenceValidationError, match="must be unique"):
        validate_pass("claims", payload, TEXT, ENTITIES)

    payload["claims"][0]["entity_ids"] = ["e2"]
    with pytest.raises(InferenceValidationError, match="monitored"):
        validate_pass("claims", payload, TEXT, ENTITIES)


def test_classification_validation_requires_every_monitored_pair_once() -> None:
    claims = [{"id": "c1", "entity_ids": ["e1", "e2"]}]
    payload = {
        "classifications": [
            {"claim_id": "c1", "entity_id": "e1", "stance": "негативне", "rhetoric": []}
        ]
    }
    validate_pass("classification", payload, TEXT, ENTITIES, claims)
    payload["classifications"][0]["stance"] = "відсутнє"
    payload["classifications"][0]["rhetoric"] = ["делегітимізація"]
    with pytest.raises(InferenceValidationError, match="rhetoric must be empty"):
        validate_pass("classification", payload, TEXT, ENTITIES, claims)

    payload["classifications"][0]["stance"] = "негативне"
    payload["classifications"][0]["rhetoric"] = ["делегітимізація", "делегітимізація"]
    with pytest.raises(InferenceValidationError, match="labels must be unique"):
        validate_pass("classification", payload, TEXT, ENTITIES, claims)


def test_json_parser_categorizes_malformed_and_non_object_values() -> None:
    assert parse_json_object('{"entities": []}') == {"entities": []}
    with pytest.raises(InferenceValidationError) as malformed:
        parse_json_object("{")
    assert malformed.value.issues[0].kind == "json_parse_failure"
    with pytest.raises(InferenceValidationError) as wrong_shape:
        parse_json_object("[]")
    assert wrong_shape.value.issues[0].kind == "schema_failure"
