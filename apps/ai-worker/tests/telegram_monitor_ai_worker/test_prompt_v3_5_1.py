"""Regression coverage for the v3.5.1 semantic prompt constraints."""

from telegram_monitor_ai_worker.prompt import (
    CLAIM_PROMPT,
    CLASSIFICATION_PROMPT,
    PROMPT_VERSIONS,
)


def test_claim_prompt_defaults_to_editorial_without_explicit_source() -> None:
    assert (
        "Без явної\nмовної атрибуції — channel_editorial. Не вигадуй зовнішнє джерело."
        in CLAIM_PROMPT
    )
    assert "за даними слідства" in CLAIM_PROMPT
    assert "Маркер джерела може керувати evidence" in CLAIM_PROMPT
    assert PROMPT_VERSIONS["claims"] == "inference_v3_claims_prompt_v6"


def test_classification_prompt_preserves_reported_attack_direction() -> None:
    assert "не призначай автоматично негативне stance щодо\nTARGET" in CLASSIFICATION_PROMPT
    assert '"X атакує Y" може бути відсутнім, позитивним або' in CLASSIFICATION_PROMPT
    assert PROMPT_VERSIONS["classification"] == "inference_v3_classification_prompt_v4"
