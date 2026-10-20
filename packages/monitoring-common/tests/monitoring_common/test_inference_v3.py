"""Contract tests for the focused inference-v3 passes."""

import pytest
from monitoring_common.contracts import (
    InferenceValidationError,
    alias_occurs,
    foreign_state_context,
    generation_schema,
    load_inference_schema,
    matched_registry_entity_ids,
    mention_is_only_foreign_state,
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
    assert alias_occurs("Шабуніним назвали активіста", "Шабунін")
    assert alias_occurs("Рішення Андрія Єрмака", "Андрій Єрмак")
    assert alias_occurs("Заява Михаила Федорова", "Михаил Федоров")
    assert not alias_occurs("Єрмаков виступив", "Єрмак")
    assert normalize_match_text("  Дар’я   КАЛЕНЮК ") == "дар’я каленюк"


def test_common_word_aliases_become_candidates_for_pass_1_to_judge() -> None:
    aliases = [
        {
            "entity_id": 22,
            "canonical_name": "Рух ЧЕСНО",
            "coarse_type": "organization",
            "monitored": True,
            "alias": "ЧЕСНО",
        },
        {
            "entity_id": 128,
            "canonical_name": "Голос",
            "coarse_type": "organization",
            "monitored": True,
            "alias": "Голос",
        },
    ]

    assert matched_registry_entity_ids("Чесно кажучи, давно його не бачив.", aliases) == [22]
    assert matched_registry_entity_ids("У ЧЕСНО заявили про порушення.", aliases) == [22]
    assert matched_registry_entity_ids("Це голос народу.", aliases) == [128]
    assert matched_registry_entity_ids("Фракція «Голос» проголосувала.", aliases) == [128]


def test_inflection_covers_feminine_adjectives_and_ist_nouns() -> None:
    party = "Європейська Солідарність"

    assert alias_occurs("членів «Європейської Солідарності» стало більше", party)
    assert alias_occurs("у Європейській Солідарності заявили", party)
    assert alias_occurs("разом із Європейською Солідарністю", party)
    assert alias_occurs("Верховної Ради", "Верховна Рада")


STATE_BODIES = [
    {
        "entity_id": 64,
        "canonical_name": "Міністерство оборони України",
        "coarse_type": "state_institution",
        "monitored": True,
        "alias": "Міноборони",
    },
    {
        "entity_id": 73,
        "canonical_name": "Міністерство закордонних справ України",
        "coarse_type": "state_institution",
        "monitored": True,
        "alias": "МЗС",
    },
]


def test_foreign_state_bodies_do_not_admit_ukrainian_registry_entities() -> None:
    assert (
        matched_registry_entity_ids("Міноборони рф заявило про збиття дронів.", STATE_BODIES) == []
    )
    assert matched_registry_entity_ids("У Міноборони Росії заявили.", STATE_BODIES) == []
    assert matched_registry_entity_ids("Китайське МЗС відповіло.", STATE_BODIES) == []
    assert matched_registry_entity_ids("Заява МЗС КНР.", STATE_BODIES) == []
    assert matched_registry_entity_ids("Міноборони повідомило про закупівлю.", STATE_BODIES) == [64]
    assert matched_registry_entity_ids(
        "Міноборони рф збрехало, а Міноборони України спростувало.", STATE_BODIES
    ) == [64]


def test_foreign_context_applies_only_to_state_bodies_and_exact_mentions() -> None:
    person = [{**STATE_BODIES[0], "coarse_type": "person", "alias": "Рф"}]
    text = "Міноборони рф заявило"

    assert foreign_state_context(text, 0, len("Міноборони"))
    assert not foreign_state_context("Міноборони заявило", 0, len("Міноборони"))
    assert mention_is_only_foreign_state(text, "Міноборони")
    assert not mention_is_only_foreign_state("Міноборони заявило", "Міноборони")
    assert not mention_is_only_foreign_state(text, "відсутня згадка")
    assert matched_registry_entity_ids("Рф виступив", person) == [64]


def test_attribution_examples_preserve_editorial_and_explicit_unnamed_sources() -> None:
    entities = [{"id": "e1", "monitored": True}]
    editorial_source = "Федоров отримав бронювання після звільнення."
    external_source = "За даними слідства, Федоров отримав бронювання після звільнення."
    editorial = {
        "claims": [
            {
                "normalized_text": editorial_source,
                "entity_ids": ["e1"],
                "evidence_text": editorial_source,
                "attribution": {"source_kind": "channel_editorial", "source_entity_id": None},
                "epistemic_status": "ствердження",
            }
        ]
    }
    external = {
        "claims": [
            {
                "normalized_text": editorial_source,
                "entity_ids": ["e1"],
                "evidence_text": editorial_source,
                "attribution": {"source_kind": "external_unnamed", "source_entity_id": None},
                "epistemic_status": "ствердження",
            }
        ]
    }

    assert (
        sanitize_pass_payload_with_actions("claims", editorial, editorial_source, entities).payload
        == editorial
    )
    assert (
        sanitize_pass_payload_with_actions("claims", external, external_source, entities).payload
        == external
    )


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
        {
            "entities": [{"mentions": ["Віталій Шабунін"]}, {"mentions": ["ЦПК"]}],
        },
        TEXT,
    )
    with pytest.raises(InferenceValidationError) as captured:
        validate_pass("entities", {"entities": [{"mentions": ["Шабуніна"]}]}, TEXT)
    assert validation_errors(captured.value)[0]["kind"] == "grounding_failure"


CANDIDATES = [{"candidate_id": "r1"}, {"candidate_id": "r2"}]


DECIDED = {"reason": "абревіатура", "same_actor": True}


def test_candidate_validation_requires_one_decision_per_candidate() -> None:
    validate_pass("candidates", {"candidates": {"r1": DECIDED, "r2": DECIDED}}, TEXT, CANDIDATES)

    with pytest.raises(InferenceValidationError, match="missing candidate: r2"):
        validate_pass("candidates", {"candidates": {"r1": DECIDED}}, TEXT, CANDIDATES)

    with pytest.raises(InferenceValidationError, match="unexpected candidate decision: r9"):
        validate_pass(
            "candidates",
            {"candidates": {"r1": DECIDED, "r2": DECIDED, "r9": DECIDED}},
            TEXT,
            CANDIDATES,
        )


def test_candidate_sanitizer_drops_unknown_candidates() -> None:
    payload = {"candidates": {"r1": DECIDED, "r9": DECIDED}}

    result = sanitize_pass_payload_with_actions("candidates", payload, TEXT, CANDIDATES)

    assert result.payload == {"candidates": {"r1": DECIDED}}
    assert [action["action"] for action in result.actions] == ["dropped_unknown_candidate"]


def test_entity_sanitizer_drops_cross_group_duplicates() -> None:
    payload = {"entities": [{"mentions": ["ЦПК"]}, {"mentions": ["ЦПК", "Віталій Шабунін"]}]}

    result = sanitize_pass_payload_with_actions("entities", payload, TEXT, ())

    assert result.payload == {
        "entities": [{"mentions": ["ЦПК"]}, {"mentions": ["Віталій Шабунін"]}]
    }
    assert [action["action"] for action in result.actions] == ["dropped_cross_group_duplicate"]


def test_generation_schema_requires_a_decision_for_every_supplied_candidate() -> None:
    schema = generation_schema(
        "candidates",
        {"candidates": [{"candidate_id": "r1"}, {"candidate_id": "r2"}]},
    )

    decisions = schema["properties"]["candidates"]
    assert decisions["required"] == ["r1", "r2"]
    assert decisions["additionalProperties"] is False
    assert decisions["properties"]["r1"]["required"] == ["reason", "same_actor"]
    assert "properties" not in load_inference_schema("candidates")["properties"]["candidates"]
    assert generation_schema("claims", {}) == load_inference_schema("claims")


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


def test_classification_sanitizer_clears_forbidden_rhetoric_without_changing_stance() -> None:
    payload = {
        "classifications": [
            {
                "claim_id": "c1",
                "entity_id": "e1",
                "stance": "відсутнє",
                "rhetoric": ["делегітимізація", "делегітимізація"],
            }
        ]
    }

    result = sanitize_pass_payload_with_actions("classification", payload, TEXT, ENTITIES)

    assert result.payload["classifications"][0] == {
        "claim_id": "c1",
        "entity_id": "e1",
        "stance": "відсутнє",
        "rhetoric": [],
    }
    assert result.actions == ({"action": "cleared_rhetoric_for_non_negative_stance", "index": 0},)


def test_json_parser_categorizes_malformed_and_non_object_values() -> None:
    assert parse_json_object('{"entities": []}') == {"entities": []}
    with pytest.raises(InferenceValidationError) as malformed:
        parse_json_object("{")
    assert malformed.value.issues[0].kind == "json_parse_failure"
    with pytest.raises(InferenceValidationError) as wrong_shape:
        parse_json_object("[]")
    assert wrong_shape.value.issues[0].kind == "schema_failure"


TARGET_CLAIMS = [
    {"claim_id": "c1", "actors": ["ЦПК", "Віталій Шабунін", "інший актор"]},
    {"claim_id": "c2", "actors": ["ЦПК", "інший актор"]},
]


def test_targets_validation_requires_each_claim_and_offered_actors() -> None:
    valid = {
        "claims": {
            "c1": {"reason": "критикує Шабуніна", "evaluated": ["Віталій Шабунін"]},
            "c2": {"reason": "нікого", "evaluated": []},
        }
    }
    validate_pass("targets", valid, TEXT, TARGET_CLAIMS)

    with pytest.raises(InferenceValidationError, match="missing claim: c2"):
        validate_pass("targets", {"claims": {"c1": valid["claims"]["c1"]}}, TEXT, TARGET_CLAIMS)

    unoffered = {
        "claims": {**valid["claims"], "c2": {"reason": "x", "evaluated": ["Віталій Шабунін"]}}
    }
    with pytest.raises(InferenceValidationError, match="not offered in c2"):
        validate_pass("targets", unoffered, TEXT, TARGET_CLAIMS)


def test_targets_sanitizer_drops_unknown_claims_and_unoffered_actors() -> None:
    payload = {
        "claims": {
            "c1": {"reason": "x", "evaluated": ["ЦПК", "ЦПК", "НАБУ"]},
            "c9": {"reason": "x", "evaluated": []},
        }
    }

    result = sanitize_pass_payload_with_actions("targets", payload, TEXT, TARGET_CLAIMS)

    assert result.payload == {"claims": {"c1": {"reason": "x", "evaluated": ["ЦПК"]}}}
    assert [action["action"] for action in result.actions] == [
        "dropped_unoffered_actor",
        "dropped_unknown_claim",
    ]


def test_targets_generation_schema_limits_each_claim_to_its_actors() -> None:
    schema = generation_schema("targets", {"claims": TARGET_CLAIMS})

    claims = schema["properties"]["claims"]
    assert claims["required"] == ["c1", "c2"]
    c2_items = claims["properties"]["c2"]["properties"]["evaluated"]["items"]
    assert c2_items["enum"] == ["ЦПК", "інший актор"]
    assert "enum" not in str(load_inference_schema("targets"))
