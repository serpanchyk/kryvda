"""Regression coverage for the v3.6 semantic prompt constraints."""

from telegram_monitor_ai_worker.prompt import (
    CLAIM_PROMPT,
    CLASSIFICATION_PROMPT,
    ENTITY_PROMPT,
    PROMPT_VERSIONS,
)


def test_entity_prompt_separates_foreign_bodies_and_keeps_named_speakers() -> None:
    assert "«Міноборони рф»" in ENTITY_PROMPT
    assert "«Янгол ЗСУ»" in ENTITY_PROMPT
    assert "навіть\nякщо вони не моніторингові" in ENTITY_PROMPT
    assert PROMPT_VERSIONS["entities"] == "inference_v3_entities_prompt_v3"


def test_claim_prompt_targets_evaluative_framing_and_news_attribution() -> None:
    assert "Не включай\n  мовця в entity_ids" in CLAIM_PROMPT
    assert "сарказмом" in CLAIM_PROMPT
    assert "«…, — X»" in CLAIM_PROMPT
    assert "за даними слідства" in CLAIM_PROMPT
    assert (
        "normalized_text, entity_ids,\nevidence_text, attribution, epistemic_status" in CLAIM_PROMPT
    )
    assert PROMPT_VERSIONS["claims"] == "inference_v3_claims_prompt_v7"


def test_classification_prompt_uses_claim_source_and_rejects_self_presentation() -> None:
    assert "claim_source" in CLASSIFICATION_PROMPT
    assert "source_is_target" in CLASSIFICATION_PROMPT
    assert "самопрезентація не є позитивною оцінкою TARGET" in CLASSIFICATION_PROMPT
    assert "нейтральний опис дій чи успіхів TARGET" in CLASSIFICATION_PROMPT
    assert PROMPT_VERSIONS["classification"] == "inference_v3_classification_prompt_v6"
