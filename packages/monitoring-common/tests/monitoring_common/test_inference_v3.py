"""Contract tests for the focused inference-v3 passes."""

import pytest
from monitoring_common.contracts import (
    InferenceValidationError,
    alias_occurs,
    matched_registry_entity_ids,
    normalize_match_text,
    parse_json_object,
    sanitize_pass_payload,
    sanitize_pass_payload_with_actions,
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
    assert alias_occurs("Шабуніна згадали", "Шабунін")
    assert alias_occurs("Рішення Андрія Єрмака", "Андрій Єрмак")
    assert alias_occurs("Заява Михаила Федорова", "Михаил Федоров")
    assert not alias_occurs("Єрмаков виступив", "Єрмак")
    assert normalize_match_text("  Дар’я   КАЛЕНЮК ") == "дар’я каленюк"


def test_registry_matching_admits_only_unique_inflected_person_surnames() -> None:
    aliases = [
        {
            "entity_id": 1,
            "alias": "Михайло Федоров",
            "coarse_type": "person",
            "monitored": True,
        },
        {
            "entity_id": 2,
            "alias": "Ігор Клименко",
            "coarse_type": "person",
            "monitored": True,
        },
        {
            "entity_id": 3,
            "alias": "Олександр Клименко",
            "coarse_type": "person",
            "monitored": True,
        },
    ]

    assert matched_registry_entity_ids("Заява Федорова", aliases) == [1]
    assert matched_registry_entity_ids("Заява Клименка", aliases) == []


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


def test_entity_validation_allows_duplicate_occurrences_inside_one_group() -> None:
    validate_pass("entities", {"entities": [{"mentions": ["ЦПК", "ЦПК"]}]}, TEXT)


def test_entity_sanitizer_deduplicates_grounds_and_drops_only_empty_groups() -> None:
    payload = {
        "entities": [
            {"mentions": ["ЦПК", "ЦПК", "not source"]},
            {"mentions": ["missing", "also missing"]},
            {"mentions": ["Віталій Шабунін", "invented"]},
        ]
    }

    sanitized = sanitize_pass_payload("entities", payload, TEXT)

    assert sanitized == {
        "entities": [
            {"mentions": ["ЦПК"]},
            {"mentions": ["Віталій Шабунін"]},
        ]
    }
    assert payload["entities"][0]["mentions"] == ["ЦПК", "ЦПК", "not source"]


def test_claim_sanitizer_keeps_relevant_items_and_records_recovery() -> None:
    payload = {
        "claims": [
            {
                "normalized_text": "ЦПК працює.",
                "entity_ids": ["e2"],
                "evidence_text": "ЦПК працює.",
                "attribution": {"source_entity_id": None, "source_kind": "channel_editorial"},
                "epistemic_status": "ствердження",
            },
            {
                "normalized_text": "Шабунін заявив.",
                "entity_ids": ["e1", "e1", "missing"],
                "evidence_text": TEXT,
                "attribution": {"source_entity_id": "e1", "source_kind": "named_entity"},
                "epistemic_status": "ствердження",
            },
        ]
    }
    result = sanitize_pass_payload_with_actions("claims", payload, TEXT, ENTITIES)

    assert len(result.payload["claims"]) == 1
    assert result.payload["claims"][0]["entity_ids"] == ["e1"]
    assert {action["action"] for action in result.actions} == {
        "dropped_claim",
        "sanitized_claim_entity_ids",
    }


def test_claim_evidence_realigns_unicode_variants_and_deduplicates() -> None:
    evidence = "«Віталій Шабунін заявив, що ЦПК працює.»"
    claim = {
        "normalized_text": "Шабунін заявив, що ЦПК працює.",
        "entity_ids": ["e1"],
        "evidence_text": evidence,
        "attribution": {"source_entity_id": "e1", "source_kind": "named_entity"},
        "epistemic_status": "ствердження",
    }
    text = evidence
    variant = {**claim, "evidence_text": "“Віталій Шабунін заявив, що ЦПК працює.”"}
    result = sanitize_pass_payload_with_actions(
        "claims", {"claims": [variant, claim]}, text, ENTITIES
    )

    assert result.payload["claims"] == [claim]
    assert {action["action"] for action in result.actions} == {
        "realigned_evidence",
        "deduplicated_claim",
    }


def test_claim_sanitizer_removes_obsolete_presentation_field() -> None:
    claim = {
        "normalized_text": "Шабунін працює.",
        "entity_ids": ["e1"],
        "evidence_text": TEXT,
        "attribution": {"source_entity_id": None, "source_kind": "channel_editorial"},
        "epistemic_status": "ствердження",
        "presentation": "цитата",
    }
    result = sanitize_pass_payload_with_actions("claims", {"claims": [claim]}, TEXT, ENTITIES)

    assert "presentation" not in result.payload["claims"][0]
    assert result.actions[0]["action"] == "removed_obsolete_presentation"


def test_runtime_schemas_avoid_unsupported_unique_items() -> None:
    from monitoring_common.contracts import load_inference_schema

    for pass_name in ("entities", "claims", "classification"):
        assert "uniqueItems" not in str(load_inference_schema(pass_name))
    claim_properties = load_inference_schema("claims")["properties"]["claims"]["items"][
        "properties"
    ]
    assert list(claim_properties)[-1:] == ["epistemic_status"]
    attribution_properties = claim_properties["attribution"]["properties"]
    assert list(attribution_properties) == ["source_entity_id", "source_kind"]


def test_claim_validation_enforces_grounding_scope_and_attribution() -> None:
    payload = {
        "claims": [
            {
                "normalized_text": "Віталій Шабунін заявив, що ЦПК працює.",
                "entity_ids": ["e1", "e2"],
                "evidence_text": TEXT,
                "attribution": {"source_kind": "named_entity", "source_entity_id": "e1"},
                "epistemic_status": "ствердження",
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
