"""Tests for backend-only inference-v3 transformations."""

from telegram_monitor_ai_worker.pipeline import (
    assign_claim_ids,
    classification_items,
    local_context,
    matched_monitored_entity_ids,
    resolve_entity_groups,
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
