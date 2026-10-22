"""Tests for backend-only inference-v3 transformations."""

from telegram_monitor_ai_worker.pipeline import (
    assign_claim_ids,
    classification_batches,
    classification_items,
    classification_subset,
    focused_claim_request,
    local_context,
    matched_monitored_entity_ids,
    merge_focused_claims,
    resolve_entity_groups,
    salvage_classification_objects,
    split_by_targets,
)

ALIASES = [
    {
        "entity_id": 10,
        "canonical_name": "Віталій Шабунін",
        "monitored": True,
        "alias": "Шабунін",
        "normalized_alias": "шабунін",
    },
    {
        "entity_id": 11,
        "canonical_name": "ЦПК",
        "monitored": False,
        "alias": "ЦПК",
        "normalized_alias": "цпк",
    },
]


def test_prefilter_and_resolution_keep_bookkeeping_out_of_model() -> None:
    assert matched_monitored_entity_ids("Шабунін і ЦПК", ALIASES) == [10]
    assert matched_monitored_entity_ids("Шабуніна згадали", ALIASES) == [10]
    resolved = resolve_entity_groups(
        [
            {"mentions": ["Шабунін"]},
            {"mentions": ["ЦПК"]},
            {"mentions": ["Олег Постернак"]},
        ],
        ALIASES,
    )
    assert [entity["id"] for entity in resolved] == ["e1", "e2", "e3"]
    assert resolved[0]["canonical_name"] == "Віталій Шабунін"
    assert resolved[2]["registry_entity_id"] is None


def test_resolution_merges_safe_registry_duplicates_and_splits_mixed_groups() -> None:
    merged = resolve_entity_groups(
        [{"mentions": ["Шабунін"]}, {"mentions": ["Віталій Шабунін"]}],
        [
            *ALIASES,
            {
                **ALIASES[0],
                "alias": "Віталій Шабунін",
                "normalized_alias": "віталій шабунін",
            },
        ],
    )
    assert merged[0]["mentions"] == ["Шабунін", "Віталій Шабунін"]

    split = resolve_entity_groups([{"mentions": ["Шабунін", "ЦПК"]}], ALIASES)
    assert [(entity["registry_entity_id"], entity["mentions"]) for entity in split] == [
        (10, ["Шабунін"]),
        (11, ["ЦПК"]),
    ]


def test_resolution_matches_inflected_registry_alias() -> None:
    resolved = resolve_entity_groups([{"mentions": ["Шабуніна"]}], ALIASES)

    assert resolved[0]["registry_entity_id"] == 10
    assert resolved[0]["monitored"] is True


def test_resolution_leaves_foreign_state_body_mentions_unresolved() -> None:
    aliases = [
        {
            "entity_id": 64,
            "canonical_name": "Міністерство оборони України",
            "coarse_type": "state_institution",
            "monitored": True,
            "alias": "Міноборони",
            "normalized_alias": "міноборони",
        }
    ]
    groups = [{"mentions": ["Міноборони"]}]

    foreign = resolve_entity_groups(groups, aliases, "Міноборони рф заявило про удар.")
    domestic = resolve_entity_groups(groups, aliases, "Міноборони заявило про закупівлю.")

    assert foreign[0]["registry_entity_id"] is None
    assert domestic[0]["registry_entity_id"] == 64


def test_claim_ids_offsets_and_local_context_are_deterministic() -> None:
    text = "Перше речення. Шабунін відповів. Третє речення. Четверте."
    claims = assign_claim_ids(
        {
            "claims": [
                {
                    "normalized_text": "Шабунін відповів.",
                    "entity_ids": ["e1"],
                    "evidence_text": "Шабунін відповів.",
                    "attribution": {
                        "source_kind": "channel_editorial",
                        "source_entity_id": None,
                    },
                    "epistemic_status": "ствердження",
                }
            ]
        },
        text,
    )
    assert claims[0]["id"] == "c1"
    assert text[claims[0]["evidence_start"] : claims[0]["evidence_end"]] == "Шабунін відповів."
    assert local_context(text, claims[0]["evidence_start"], claims[0]["evidence_end"]) == (
        "Перше речення. Шабунін відповів. Третє речення."
    )

    items = classification_items(
        text,
        [
            {
                "id": "e1",
                "mentions": ["Шабунін"],
                "canonical_name": "Віталій Шабунін",
                "monitored": True,
            }
        ],
        claims,
    )
    assert items[0]["target"] == "Віталій Шабунін"
    assert items[0]["local_context"].startswith("Перше")


def test_classification_items_name_the_claim_source() -> None:
    text = "Шабунін заявив, що ЦПК працює. Канал вважає інакше."
    entities = [
        {
            "id": "e1",
            "mentions": ["Шабунін"],
            "canonical_name": "Віталій Шабунін",
            "monitored": True,
        },
        {"id": "e2", "mentions": ["ЦПК"], "canonical_name": "ЦПК", "monitored": True},
    ]
    claims = [
        {
            "id": "c1",
            "entity_ids": ["e1", "e2"],
            "normalized_text": "Шабунін заявив, що ЦПК працює.",
            "evidence_text": "Шабунін заявив, що ЦПК працює.",
            "evidence_start": 0,
            "evidence_end": 30,
            "attribution": {"source_kind": "named_entity", "source_entity_id": "e1"},
        },
        {
            "id": "c2",
            "entity_ids": ["e2"],
            "normalized_text": "Канал вважає інакше.",
            "evidence_text": "Канал вважає інакше.",
            "evidence_start": 31,
            "evidence_end": 51,
            "attribution": {"source_kind": "external_unnamed", "source_entity_id": None},
        },
    ]

    items = classification_items(text, entities, claims)

    assert [(item["claim_source"], item["source_is_target"]) for item in items] == [
        ("Віталій Шабунін", True),
        ("Віталій Шабунін", False),
        ("неназване джерело", False),
    ]


def test_classification_batches_and_salvage_keep_only_complete_objects() -> None:
    items = [{"claim_id": f"c{index}", "entity_id": "e1"} for index in range(1, 7)]
    assert [[item["claim_id"] for item in batch] for batch in classification_batches(items, 5)] == [
        ["c1", "c2", "c3", "c4", "c5"],
        ["c6"],
    ]
    raw = '''{"classifications":[
      {"claim_id":"c1","entity_id":"e1","stance":"негативне","rhetoric":[]},
      {"claim_id":"c2","entity_id":"e1","stance":"негативне","rhetoric":[]},
      {"claim_id":"c3"'''
    assert [item["claim_id"] for item in salvage_classification_objects(raw)] == ["c1", "c2"]


def test_classification_subset_clears_rhetoric_for_non_negative_stance() -> None:
    payload = {
        "classifications": [
            {
                "claim_id": "c1",
                "entity_id": "e1",
                "stance": "позитивне",
                "rhetoric": ["корупція_або_особиста_вигода"],
            }
        ]
    }
    entities = [{"id": "e1", "monitored": True}]
    claims = [{"id": "c1", "entity_ids": ["e1"]}]

    retained, missing, actions = classification_subset(payload, entities, claims)

    assert retained == [
        {"claim_id": "c1", "entity_id": "e1", "stance": "позитивне", "rhetoric": []}
    ]
    assert missing == []
    assert actions == [{"action": "cleared_rhetoric_for_non_negative_stance", "index": 0}]


def test_focused_claim_request_names_one_monitored_entity() -> None:
    entities = [
        {
            "id": "e1",
            "canonical_name": "Віталій Шабунін",
            "mentions": ["Шабунін"],
            "monitored": True,
        },
        {"id": "e2", "canonical_name": None, "mentions": ["Іванов"], "monitored": False},
    ]

    request = focused_claim_request("Шабунін і Іванов.", entities, entities[0])

    assert request["focus_entity_id"] == "e1"
    assert request["focus_entity"] == "Віталій Шабунін"
    assert request["entities"] == entities


def test_merge_focused_claims_unites_entities_of_the_same_quote_and_source() -> None:
    editorial = {"source_kind": "channel_editorial", "source_entity_id": None}

    def claim(text: str, entity_ids: list[str], source: dict[str, object]) -> dict[str, object]:
        return {
            "normalized_text": text,
            "entity_ids": entity_ids,
            "evidence_text": "НАБУ відбілює ЦПК",
            "attribution": source,
            "epistemic_status": "ствердження",
        }

    quoted = {"source_kind": "named_entity", "source_entity_id": "e3"}
    merged = merge_focused_claims(
        [
            {"claims": [claim("НАБУ відбілює ЦПК.", ["e1"], editorial)]},
            {"claims": [claim("ЦПК відбілюють.", ["e2", "e1"], editorial)]},
            {"claims": [claim("Цитата.", ["e2"], quoted)]},
        ]
    )

    assert [item["entity_ids"] for item in merged["claims"]] == [["e1", "e2"], ["e2"]]
    assert merged["claims"][0]["normalized_text"] == "НАБУ відбілює ЦПК."


def test_split_by_targets_hints_the_direction_and_marks_the_rest_absent() -> None:
    items = [
        {"claim_id": "c1", "entity_id": "e1", "target": "СБУ"},
        {"claim_id": "c1", "entity_id": "e2", "target": "НАБУ"},
        {"claim_id": "c1", "entity_id": "e3", "target": "ЦПК"},
    ]
    decisions = {
        "claims": {
            "c1": {"reason": "x", "criticized": ["НАБУ", "ЦПК"], "supported": ["СБУ", "ЦПК"]}
        }
    }

    to_classify, absent = split_by_targets(items, decisions)

    assert [(item["target"], item["evaluation"]) for item in to_classify] == [
        ("СБУ", "підтримує"),
        ("НАБУ", "критикує"),
        ("ЦПК", "критикує і підтримує"),
    ]
    assert absent == []
    _, absent = split_by_targets(items, {"claims": {"c1": {"criticized": [], "supported": []}}})
    assert [row["stance"] for row in absent] == ["відсутнє"] * 3
