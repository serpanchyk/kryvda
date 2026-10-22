"""Regression coverage for the inference v4 semantic prompt constraints."""

from telegram_monitor_ai_worker.prompt import (
    CANDIDATE_PROMPT,
    CLAIM_PROMPT,
    CLASSIFICATION_PROMPT,
    ENTITY_PROMPT,
    PROMPT_VERSIONS,
    SYSTEM_PROMPTS,
    TARGET_PROMPT,
)


def test_candidate_prompt_judges_lexical_registry_matches_in_context() -> None:
    assert "contexts" in CANDIDATE_PROMPT
    assert "особа, орган чи організація з реєстру" in CANDIDATE_PROMPT
    assert "(«Чесна мобілізація» не є Рухом ЧЕСНО)" in CANDIDATE_PROMPT
    assert "не за великими літерами" in CANDIDATE_PROMPT
    assert "Якщо сумніваєшся, став\ntrue." in CANDIDATE_PROMPT
    assert PROMPT_VERSIONS["candidates"] == "inference_v3_candidates_prompt_v1"


def test_entity_prompt_keeps_the_v3_6_rules_against_repeated_mentions() -> None:
    assert "Ніколи не повторюй той самий рядок" in ENTITY_PROMPT
    assert "«Янгол ЗСУ»" in ENTITY_PROMPT
    assert PROMPT_VERSIONS["entities"] == "inference_v3_entities_prompt_v4"


def test_claim_prompt_keeps_background_entities_out_of_claim_targets() -> None:
    assert "«протеже Андрія Єрмака»" in CLAIM_PROMPT
    assert "лише нейтральним тлом" in CLAIM_PROMPT
    assert "Не включай\n  мовця в entity_ids" in CLAIM_PROMPT
    assert "«…, — X»" in CLAIM_PROMPT
    assert (
        "normalized_text, entity_ids,\nevidence_text, attribution, epistemic_status" in CLAIM_PROMPT
    )
    assert "focus_entity_id" in CLAIM_PROMPT
    assert PROMPT_VERSIONS["claims"] == "inference_v3_claims_prompt_v9"


def test_targets_prompt_asks_for_every_evaluated_actor_by_name() -> None:
    assert "actors — усі актори твердження" in TARGET_PROMPT
    assert "«інший актор або ніхто з\nпереліку»" in TARGET_PROMPT
    assert "оцінюються ВАКС, САП і НАБУ" in TARGET_PROMPT
    assert "імена з actors УСІХ, кого оцінюють" in TARGET_PROMPT
    assert "вигідне подання актора — теж оцінка" in TARGET_PROMPT
    assert PROMPT_VERSIONS["targets"] == "inference_v3_targets_prompt_v4"


def test_classification_prompt_counts_a_positive_context_as_positive() -> None:
    assert "claim_source" in CLASSIFICATION_PROMPT
    assert "учасник чи об'єкт негативної події" in CLASSIFICATION_PROMPT
    assert "у позитивному світлі, навіть без прямої похвали" in CLASSIFICATION_PROMPT
    assert "результати опитувань" not in CLASSIFICATION_PROMPT
    assert PROMPT_VERSIONS["classification"] == "inference_v3_classification_prompt_v8"


def test_affiliation_prompt_links_people_only_through_the_post() -> None:
    assert "голова ЦПК Віталій Шабунін" in SYSTEM_PROMPTS["affiliations"]
    assert "Не додавай організацію з\nвласних знань" in SYSTEM_PROMPTS["affiliations"]
    assert PROMPT_VERSIONS["affiliations"] == "inference_v3_affiliations_prompt_v1"
