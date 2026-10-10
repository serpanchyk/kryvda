"""Evaluate Jev typed decisions on reviewed golden_v0 claims, classification only.

The run isolates classification from extraction: every request carries the reviewed claims, their
attribution, and the production Pass 3 local context, and Jev answers only typed questions. Its
metrics therefore measure stance, rhetoric, epistemic status, and presentation, never claim
coverage or attribution, which are supplied inputs.
"""

import argparse
import asyncio
import json
import logging
import os
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol, cast

import httpx
from golden_report import (
    EvaluationItem,
    _confusion,
    _prf,
    _ratio,
    benchmark_report,
    canonical_prediction,
    extension_example_ids,
)
from golden_schema import (
    EPISTEMIC_MAP,
    RHETORIC_MAP,
    CanonicalGolden,
    GoldenClassification,
    _spans_overlap,
    load_golden,
    load_golden_jsonl,
)
from mamay_golden_v2 import completed_example_ids, semantic_benchmark_report
from monitoring_common.logging import setup_logging
from telegram_monitor_ai_worker.pipeline import local_context

SCHEMA_VERSION = "jev_vs_golden_v1"
DEFAULT_ANNOTATIONS = Path("experiments/datasets/golden_v0/data/annotations.jsonl")
DEFAULT_OUTPUT = Path("experiments/dspy/data/jev_vs_golden_v1/responses.jsonl")
DEFAULT_MAMAY = Path("experiments/dspy/data/mamay_vs_golden_v3_5_2/comparisons.jsonl")
DEFAULT_OLD55 = Path("experiments/dspy/data/mamay_vs_golden_v3_5/comparisons.jsonl")
DEFAULT_MODEL = "~typesafe/jev-latest"
DEFAULT_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_THRESHOLD = 0.5
SWEEP_THRESHOLDS = (0.3, 0.4, 0.5, 0.6, 0.7)
NEGATIVE_GRID = (0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5)
RHETORIC_GRID = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
SEPARATOR = "__"

GUIDELINES = """Ти класифікуєш уже витягнуті твердження (claims) з Telegram-постів для моніторингу
атак на антикорупційних акторів. Оцінюй лише текст поста, без зовнішніх знань.

Current perspective — це автор claim з поля author: редакція каналу, названий актор або
неназване стороннє джерело. Stance описує лише ставлення current perspective до TARGET, а не
ставлення іншого актора, згаданого всередині proposition. Негативна подія, звинувачення,
критика, атака, розслідування, затримання, опитування чи санкція за участю TARGET самі по собі
не є негативним stance. "X атакує Y" не означає, що канал негативно ставиться до Y. Опитування
("40% не довіряють TARGET") описує респондентів, а не current perspective.

Rhetoric — це спостережуваний у тексті прийом проти TARGET, окремий від stance. Сама згадка
грошей, гранту, зарплати чи великої суми не є корупцією без явного означення збагачення.
Загальна критика ("ЦПК маніпулює фактами") не є лицемірством без чіткого контрасту між
заявленими принципами і поведінкою."""

STANCE_CRITERIA = {
    "позитивне": "current perspective сама позитивно оцінює TARGET, хвалить чи підтримує його",
    "негативне": (
        "current perspective сама негативно характеризує TARGET, підтримує таку характеристику "
        "або подає її як власну оцінку"
    ),
    "відсутнє": (
        "current perspective не має власної істотної оцінки TARGET; чужа атака, критика, "
        "звинувачення, розслідування, опитування чи нейтрально описана негативна подія за участю "
        "TARGET сюди належать"
    ),
}
RHETORIC_CRITERIA = {
    "corruption_accusation": (
        "явне звинувачення в корупції, хабарях, відкатах, особистому збагаченні чи захисті "
        "союзника заради вигоди"
    ),
    "criminality_accusation": (
        "явне звинувачення у злочині, шахрайстві, порушенні закону чи кримінальній участі"
    ),
    "delegitimization": (
        "атака на легітимність, компетентність, незалежність, авторитет, інституційну роль чи "
        "здатність виконувати функцію"
    ),
    "hypocrisy_claim": (
        "чіткий контраст між заявленими принципами, місією чи попередньою критикою TARGET і його "
        "нібито поточною поведінкою"
    ),
    "ridicule": "глузування, сарказм, іронія чи принизлива метафора",
    "derogatory_labeling": "образливий ярлик, лайливе прізвисько чи принизливе означення",
    "foreign_control_accusation": (
        "явний зовнішній контроль, дія в інтересах іншої держави, нелояльність Україні чи "
        "framing агента впливу"
    ),
    "grant_discrediting": (
        "дискредитація через гранти чи іноземне фінансування: грантоїди, робота за гранти, "
        "фінансування як доказ продажності"
    ),
    "call_for_punishment": (
        "заклик покарати, звільнити, ув'язнити, ліквідувати, заборонити чи санкціонувати TARGET"
    ),
}
EPISTEMIC_CRITERIA = {
    "asserted": "твердження подано як встановлений факт",
    "alleged": "підозра, звинувачення, версія слідства, 'нібито' чи непідтверджена інформація",
    "denied": "твердження явно заперечується або спростовується",
    "hypothetical": "припущення, можливість, умовний чи прогнозований сценарій",
    "questioned": "справжнє або риторичне питання",
}
PRESENTATION_CRITERIA = {
    "editorial": "власний текст каналу, його голос",
    "direct_quote": "пряма цитата чиїхось слів",
    "reported": "переказ чужих слів чи позиції без прямої цитати",
    "repost": "переслане чи повністю запозичене повідомлення іншого джерела",
}
AUTHOR_LABELS = {
    "channel_editorial": "редакція каналу",
    "external_unnamed": "неназване стороннє джерело",
    "unknown": "невідоме джерело",
}

# v2 answers the v1 failure modes observed on old55 only: Jev under-called an author's own attack
# (the Mamay-oriented "another actor's attack" rule leaked onto named authors), missed insinuation,
# and read "X стверджує" in the normalized claim as uncertainty.
GUIDELINES_V2 = """Ти класифікуєш уже витягнуті твердження (claims) з Telegram-постів для
моніторингу інформаційних атак на антикорупційних акторів. Оцінюй лише текст поста.

Кожен claim має author — того, чию позицію він передає: редакцію каналу, названого актора або
неназване джерело. Питання про ставлення стосуються саме author, а не каналу загалом.
- Якщо author сам звинувачує, критикує, висміює чи дискредитує TARGET, це негативне ставлення
  author, навіть коли author не канал. "Постернак стверджує, що в НАБУ можна безкарно
  збагачуватися" означає, що Постернак негативно ставиться до НАБУ.
- Якщо author лише переказує, що хтось інший атакує TARGET, і сам до атаки не приєднується,
  ставлення author до TARGET відсутнє. "Канал повідомляє, що депутат X критикує НАБУ" не означає,
  що канал оцінює НАБУ.
- Негативне ставлення буває непрямим: натяк через зіставлення фактів ("отримав посаду у фонді
  наступного дня після звільнення"), іронія, лапки, оцінні слова, добір дискредитувальних фактів.
- Нейтральна новина про подію з TARGET (затримання, суд, розслідування, заява) без оцінних слів
  чи натяків не є ставленням.

Поле claim — нормалізований переказ. Слова "стверджує", "повідомляє", "заявляє" в ньому лише
вказують на author і нічого не кажуть про впевненість. Для епістемічного статусу й presentation
орієнтуйся на evidence і context, тобто на оригінальне формулювання поста."""

RHETORIC_CRITERIA_V2 = {
    "corruption_accusation": (
        "звинувачення в корупції, хабарях, відкатах, розкраданні, незаконному збагаченні чи "
        "конфлікті інтересів заради вигоди ('отримав хабар', 'збагатився на закупівлях'); сама "
        "згадка гранту, зарплати чи великої суми не рахується"
    ),
    "criminality_accusation": (
        "звинувачення у злочині, шахрайстві, незаконних діях, кримінальній участі чи покриванні "
        "злочинців"
    ),
    "delegitimization": (
        "атака на легітимність, компетентність, незалежність чи право TARGET виконувати свою роль "
        "('імітує роботу', 'кишеньковий орган', 'провалив', 'не має права')"
    ),
    "hypocrisy_claim": (
        "контраст між заявленими принципами чи критикою TARGET і його власною поведінкою "
        "('борці з корупцією самі...', 'декларують X, але роблять Y')"
    ),
    "ridicule": "глузування, сарказм, іронічні лапки, принизлива метафора чи жарт над TARGET",
    "derogatory_labeling": (
        "образливий ярлик чи прізвисько для TARGET ('грантоїди', 'соросята', 'корупціонери')"
    ),
    "foreign_control_accusation": (
        "TARGET нібито діє в інтересах чи під контролем іноземних держав, фондів чи кураторів "
        "('працює на Сороса', 'зовнішнє управління', 'агенти впливу')"
    ),
    "grant_discrediting": (
        "дискредитація TARGET через гранти чи іноземне фінансування ('живуть на гранти', "
        "'відпрацьовують гроші донорів', 'грантоїди'), фінансування як доказ продажності"
    ),
    "call_for_punishment": (
        "заклик чи вимога покарати TARGET: звільнити, посадити, ліквідувати, заборонити, "
        "перевірити чи запровадити санкції"
    ),
}
EPISTEMIC_CRITERIA_V2 = {
    "asserted": (
        "author подає proposition як факт, зокрема власні звинувачення чи оцінки без маркерів "
        "сумніву ('X вкрав', 'суд встановив', 'джерела повідомляють, що X зробив Y')"
    ),
    "alleged": (
        "саме формулювання evidence маркує непевність: 'нібито', 'ймовірно', 'за версією "
        "слідства', 'підозрюють', 'можливо причетний'"
    ),
    "denied": "evidence заперечує чи спростовує proposition ('це неправда', 'не причетний')",
    "hypothetical": "умовний, прогнозований чи можливий сценарій ('якщо', 'може', 'буде')",
    "questioned": "proposition подано як питання, зокрема риторичне",
}


@dataclass(frozen=True)
class PromptSet:
    """One versioned question design; responses record which version produced them."""

    guidelines: str
    rhetoric: Mapping[str, str]
    epistemic: Mapping[str, str]
    decomposed_stance: bool
    rhetoric_template: str
    rhetoric_as_choice: bool = False


PROMPTS = {
    "v1": PromptSet(
        GUIDELINES,
        RHETORIC_CRITERIA,
        EPISTEMIC_CRITERIA,
        decomposed_stance=False,
        rhetoric_template="Ймовірність, що author claim {claim} застосовує щодо {target} прийом: "
        "{description}.",
    ),
    "v2": PromptSet(
        GUIDELINES_V2,
        RHETORIC_CRITERIA_V2,
        EPISTEMIC_CRITERIA_V2,
        decomposed_stance=True,
        rhetoric_template="Чи claim {claim} у своєму evidence і context застосовує проти {target} "
        "прийом: {description}?",
    ),
    # v3 and v4 address v2 rhetoric false positives on old55: labels spilled from neighbouring
    # context sentences onto every claim, while golden_v0 records only the salient device.
    "v3": PromptSet(
        GUIDELINES_V2,
        RHETORIC_CRITERIA_V2,
        EPISTEMIC_CRITERIA_V2,
        decomposed_stance=True,
        rhetoric_template="Чи саме proposition claim {claim} та його evidence, а не сусідні "
        "речення з context, явно застосовує проти {target} прийом: {description}? Познач лише "
        "прийом, що є суттю цього claim.",
    ),
    "v4": PromptSet(
        GUIDELINES_V2,
        RHETORIC_CRITERIA_V2,
        EPISTEMIC_CRITERIA_V2,
        decomposed_stance=True,
        rhetoric_template="Головний риторичний прийом, який claim {claim}, тобто лише його "
        "evidence, а не сусідні речення з context, застосовує проти {target}.",
        rhetoric_as_choice=True,
    ),
}
NO_RHETORIC = "none"
NO_RHETORIC_CRITERION = (
    "жодного явного прийому: нейтральний факт, переказ без оцінки чи оцінка без конкретного прийому"
)
SECOND_RHETORIC_PROBABILITY = 0.25


class DecisionClient(Protocol):
    """Typed-decision boundary used by the generator."""

    async def decide(self, request: Mapping[str, Any]) -> dict[str, Any]: ...


class OpenRouterDecisionClient:
    """Call OpenRouter's decisions endpoint with bounded retries for transient failures."""

    def __init__(
        self,
        url: str,
        api_key: str,
        timeout_seconds: float = 120,
        attempts: int = 4,
        backoff_seconds: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._attempts = attempts
        self._backoff_seconds = backoff_seconds
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )

    async def decide(self, request: Mapping[str, Any]) -> dict[str, Any]:
        for attempt in range(1, self._attempts + 1):
            try:
                response = await self._client.post(self._url, json=request)
            except httpx.TransportError:
                if attempt == self._attempts:
                    raise
            else:
                if response.status_code not in RETRYABLE_STATUS or attempt == self._attempts:
                    response.raise_for_status()
                    body = response.json()
                    if not isinstance(body, dict):
                        raise ValueError("decision response must be an object")
                    return body
            await asyncio.sleep(self._backoff_seconds * 2**attempt)
        raise RuntimeError("unreachable retry state")

    async def close(self) -> None:
        await self._client.aclose()


@dataclass(frozen=True)
class PairDecision:
    stance: str
    stance_probabilities: dict[str, float]
    rhetoric: dict[str, float]


@dataclass(frozen=True)
class ClaimDecision:
    epistemic: str
    presentation: str


def entity_names(record: Mapping[str, Any]) -> dict[str, str]:
    """Return a readable name for every reviewed entity."""
    return {
        entity["id"]: entity.get("canonical_name") or entity["surface_form"]
        for entity in record["annotations"]["entities"]
    }


def author_label(attribution: Mapping[str, Any], names: Mapping[str, str]) -> str:
    """Describe the claim's current perspective in the request."""
    kind = attribution.get("source_kind")
    source_id = attribution.get("source_entity_id")
    if kind == "named_entity":
        name = names.get(source_id) if isinstance(source_id, str) else None
        return f"названий актор: {name}" if name else "названий актор"
    return AUTHOR_LABELS.get(str(kind), "невідоме джерело")


def build_questions(
    golden: CanonicalGolden, names: Mapping[str, str], prompts: PromptSet = PROMPTS["v1"]
) -> dict[str, Any]:
    """Return every typed question for one example, keyed by claim and target."""
    questions: dict[str, Any] = {}
    targets: dict[str, list[str]] = {}
    for classification in golden.classifications:
        targets.setdefault(classification.claim_id, []).append(classification.entity_id)
    for claim in golden.claims:
        questions[f"{claim.id}{SEPARATOR}epistemic"] = {
            "type": "choice",
            "instructions": f"Епістемічний статус claim {claim.id}.",
            "criteria": prompts.epistemic,
        }
        questions[f"{claim.id}{SEPARATOR}presentation"] = {
            "type": "choice",
            "instructions": f"Як пост подає claim {claim.id}.",
            "criteria": PRESENTATION_CRITERIA,
        }
        for entity_id in targets.get(claim.id, []):
            target = names.get(entity_id, entity_id)
            prefix = f"{claim.id}{SEPARATOR}{entity_id}{SEPARATOR}"
            if prompts.decomposed_stance:
                questions[f"{prefix}own_negative"] = {
                    "type": "noul",
                    "instructions": (
                        f"Чи author claim {claim.id} сам негативно оцінює, звинувачує, критикує, "
                        f"висміює чи дискредитує {target}, прямо або натяком, а не лише переказує "
                        "чужу атаку?"
                    ),
                }
                questions[f"{prefix}own_positive"] = {
                    "type": "noul",
                    "instructions": (
                        f"Чи author claim {claim.id} сам позитивно оцінює, хвалить, захищає чи "
                        f"підтримує {target}?"
                    ),
                }
            else:
                questions[f"{prefix}stance"] = {
                    "type": "choice",
                    "instructions": (
                        f"Stance current perspective (author) claim {claim.id} щодо "
                        f"TARGET={target}."
                    ),
                    "criteria": STANCE_CRITERIA,
                }
            if prompts.rhetoric_as_choice:
                questions[f"{prefix}rhetoric_main"] = {
                    "type": "choice",
                    "instructions": prompts.rhetoric_template.format(claim=claim.id, target=target),
                    "criteria": dict(prompts.rhetoric) | {NO_RHETORIC: NO_RHETORIC_CRITERION},
                }
                continue
            for label, description in prompts.rhetoric.items():
                questions[f"{prefix}rhetoric{SEPARATOR}{label}"] = {
                    "type": "noul",
                    "instructions": prompts.rhetoric_template.format(
                        claim=claim.id, target=target, description=description
                    ),
                }
    return questions


def build_requests(
    golden: CanonicalGolden,
    names: Mapping[str, str],
    model: str,
    max_questions: int,
    prompts: PromptSet = PROMPTS["v1"],
) -> list[dict[str, Any]]:
    """Split one example into bounded requests that never divide a claim's questions."""
    if max_questions < 1:
        raise ValueError("max_questions must be at least one")
    claims_by_id = {claim.id: claim for claim in golden.claims}
    by_claim: dict[str, dict[str, Any]] = {}
    for key, question in build_questions(golden, names, prompts).items():
        by_claim.setdefault(key.split(SEPARATOR, 1)[0], {})[key] = question
    chunks: list[dict[str, Any]] = []
    for claim_id, questions in by_claim.items():
        if chunks and len(chunks[-1]) + len(questions) <= max_questions:
            chunks[-1].update(questions)
        else:
            chunks.append(dict(questions))
    requests: list[dict[str, Any]] = []
    for questions in chunks:
        claim_ids = dict.fromkeys(key.split(SEPARATOR, 1)[0] for key in questions)
        state_claims = {}
        for claim_id in claim_ids:
            claim = claims_by_id[claim_id]
            context = (
                local_context(golden.source_text, claim.evidence_start, claim.evidence_end)
                if claim.evidence_start is not None and claim.evidence_end is not None
                else claim.evidence_text
            )
            state_claims[claim_id] = {
                "claim": claim.normalized_text,
                "evidence": claim.evidence_text,
                "context": context,
                "author": author_label(claim.attribution, names),
            }
        requests.append(
            {
                "model": model,
                "state": {"guidelines": prompts.guidelines, "claims": state_claims},
                "questions": questions,
            }
        )
    return requests


async def analyze_record(
    record: Mapping[str, Any],
    client: DecisionClient,
    model: str,
    max_questions: int,
    prompt_version: str = "v1",
) -> dict[str, Any]:
    """Return one auditable row with every raw request and response."""
    golden = load_golden(record)
    requests = build_requests(
        golden, entity_names(record), model, max_questions, PROMPTS[prompt_version]
    )
    responses: list[dict[str, Any]] = []
    row: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "input": {"example_id": golden.example_id},
        "prompt_version": prompt_version,
        "requests": requests,
        "responses": responses,
    }
    try:
        for request in requests:
            started = time.monotonic()
            body = await client.decide(request)
            responses.append({"latency_seconds": time.monotonic() - started, "body": body})
    except (httpx.HTTPError, ValueError) as error:
        return row | {"status": "failed", "error": f"{type(error).__name__}: {error}"}
    return row | {"status": "completed", "error": None}


async def generate_responses(
    records: Sequence[Mapping[str, Any]],
    output_path: Path,
    client: DecisionClient,
    logger: logging.Logger,
    model: str = DEFAULT_MODEL,
    max_questions: int = 80,
    concurrency: int = 4,
    prompt_version: str = "v1",
) -> tuple[int, int]:
    """Append missing example rows and return written/failed counts."""
    if concurrency < 1:
        raise ValueError("concurrency must be at least one")
    completed = completed_example_ids(output_path)
    pending = [record for record in records if record["example_id"] not in completed]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    failed = 0

    async def process(record: Mapping[str, Any]) -> None:
        nonlocal failed
        async with semaphore:
            row = await analyze_record(record, client, model, max_questions, prompt_version)
        async with lock:
            with output_path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
            failed += row["status"] != "completed"
            logger.info(
                "jev_golden_example_written",
                extra={"example_id": record["example_id"], "status": row["status"]},
            )

    await asyncio.gather(*(process(record) for record in pending))
    return len(pending), failed


def merged_answers(row: Mapping[str, Any]) -> dict[str, Any]:
    """Merge the answers of every request in one row."""
    answers: dict[str, Any] = {}
    for response in row["responses"]:
        answers.update(response["body"]["answers"])
    return answers


def decode_answers(
    answers: Mapping[str, Any],
) -> tuple[dict[tuple[str, str], PairDecision], dict[str, ClaimDecision]]:
    """Convert raw typed answers into pair-level and claim-level decisions."""
    stances: dict[tuple[str, str], Mapping[str, Any]] = {}
    own: dict[tuple[str, str], dict[str, float]] = {}
    rhetoric: dict[tuple[str, str], dict[str, float]] = {}
    claim_fields: dict[str, dict[str, str]] = {}
    for key, answer in answers.items():
        parts = key.split(SEPARATOR)
        if len(parts) == 2:
            claim_fields.setdefault(parts[0], {})[parts[1]] = answer["choice"]
        elif len(parts) == 3 and parts[2] == "stance":
            stances[(parts[0], parts[1])] = answer
        elif len(parts) == 3 and parts[2] == "rhetoric_main":
            rhetoric[(parts[0], parts[1])] = main_rhetoric(answer)
        elif len(parts) == 3 and parts[2] in {"own_negative", "own_positive"}:
            own.setdefault((parts[0], parts[1]), {})[parts[2]] = float(answer["noul"])
        elif len(parts) == 4 and parts[2] == "rhetoric":
            rhetoric.setdefault((parts[0], parts[1]), {})[parts[3]] = float(answer["noul"])
    pairs = {
        pair: PairDecision(
            stance=answer["choice"],
            stance_probabilities={
                label: float(value) for label, value in answer["probabilities"].items()
            },
            rhetoric=rhetoric.get(pair, {}),
        )
        for pair, answer in stances.items()
    }
    for pair, values in own.items():
        pairs[pair] = decomposed_stance(
            values.get("own_negative", 0.0), values.get("own_positive", 0.0), rhetoric.get(pair, {})
        )
    claims = {
        claim_id: ClaimDecision(fields["epistemic"], fields["presentation"])
        for claim_id, fields in claim_fields.items()
        if "epistemic" in fields and "presentation" in fields
    }
    return pairs, claims


def main_rhetoric(answer: Mapping[str, Any]) -> dict[str, float]:
    """Select the main device and at most one runner-up, fixed before scoring."""
    if answer["choice"] == NO_RHETORIC:
        return {}
    probabilities = {
        label: float(value)
        for label, value in answer["probabilities"].items()
        if label != NO_RHETORIC
    }
    ranked = sorted(probabilities, key=lambda label: -probabilities[label])
    selected = [answer["choice"]] + [
        label
        for label in ranked
        if label != answer["choice"] and probabilities[label] >= SECOND_RHETORIC_PROBABILITY
    ][:1]
    return {label: 1.0 for label in selected}


def decomposed_stance(
    negative: float, positive: float, rhetoric: Mapping[str, float]
) -> PairDecision:
    """Combine the author's own negative and positive evaluation probabilities into a stance."""
    if negative >= DEFAULT_THRESHOLD and negative >= positive:
        stance = "негативне"
    elif positive >= DEFAULT_THRESHOLD:
        stance = "позитивне"
    else:
        stance = "відсутнє"
    return PairDecision(
        stance,
        {"негативне": negative, "позитивне": positive, "відсутнє": 1 - max(negative, positive)},
        dict(rhetoric),
    )


def production_rhetoric(
    decision: PairDecision, threshold: float, gated: bool = True, cap: int | None = 2
) -> list[str]:
    """Project extended rhetoric probabilities onto the production label set."""
    if gated and decision.stance != "негативне":
        return []
    scores: dict[str, float] = {}
    for label, probability in decision.rhetoric.items():
        mapped = RHETORIC_MAP.get(label)
        if mapped is not None and probability >= threshold:
            scores[mapped] = max(scores.get(mapped, 0.0), probability)
    ranked = sorted(scores, key=lambda label: -scores[label])
    return ranked if cap is None else ranked[:cap]


def calibrated_stance(decision: PairDecision, negative_threshold: float | None) -> PairDecision:
    """Select negative stance from its probability instead of Jev's argmax choice."""
    if negative_threshold is None:
        return decision
    probabilities = decision.stance_probabilities
    if probabilities.get("негативне", 0.0) >= negative_threshold:
        stance = "негативне"
    elif decision.stance != "негативне":
        stance = decision.stance
    else:
        stance = max(("позитивне", "відсутнє"), key=lambda label: probabilities.get(label, 0.0))
    return replace(decision, stance=stance)


def production_prediction(
    golden: CanonicalGolden,
    pairs: Mapping[tuple[str, str], PairDecision],
    claims: Mapping[str, ClaimDecision],
    threshold: float,
    allowed_pairs: set[tuple[str, str]] | None = None,
    allowed_claims: set[str] | None = None,
    negative_threshold: float | None = None,
) -> CanonicalGolden:
    """Build a canonical prediction in production taxonomy over the reviewed claims."""
    predicted_claims = [
        replace(claim, epistemic_status=EPISTEMIC_MAP.get(claims[claim.id].epistemic))
        for claim in golden.claims
        if claim.id in claims and (allowed_claims is None or claim.id in allowed_claims)
    ]
    classifications = [
        GoldenClassification(
            item.claim_id,
            item.entity_id,
            decision.stance,
            production_rhetoric(decision, threshold),
        )
        for item in golden.classifications
        if (found := pairs.get((item.claim_id, item.entity_id))) is not None
        and (decision := calibrated_stance(found, negative_threshold))
        and (allowed_pairs is None or (item.claim_id, item.entity_id) in allowed_pairs)
    ]
    return CanonicalGolden(
        example_id=golden.example_id,
        source_text=golden.source_text,
        entities=golden.entities,
        claims=predicted_claims,
        classifications=classifications,
        original_schema_version=SCHEMA_VERSION,
    )


def extended_rhetoric_gold(
    record: Mapping[str, Any], golden: CanonicalGolden
) -> dict[tuple[str, str], set[str]]:
    """Attach every reviewed rhetoric feature, including unmapped ones, to its pair."""
    gold: dict[tuple[str, str], set[str]] = {
        (item.claim_id, item.entity_id): set() for item in golden.classifications
    }
    for feature in record["annotations"]["rhetorical_features"]:
        target = feature.get("target_entity_id")
        if not isinstance(target, str):
            continue
        candidates = [claim for claim in golden.claims if target in claim.entity_ids]
        target_claim = feature.get("target_claim_id")
        if isinstance(target_claim, str):
            candidates = [claim for claim in candidates if claim.id == target_claim]
        elif isinstance(feature.get("evidence_span"), Mapping):
            span = [feature["evidence_span"]]
            candidates = [claim for claim in candidates if _spans_overlap(claim, span)]
        else:
            continue
        if len(candidates) == 1 and (candidates[0].id, target) in gold:
            gold[(candidates[0].id, target)].add(feature["feature_type"])
    return gold


def _labelled_metrics(
    pairs: Sequence[tuple[set[str], set[str]]], labels: Iterable[str]
) -> dict[str, Any]:
    per_label = {}
    for label in labels:
        per_label[label] = _prf(
            sum(label in gold and label in predicted for gold, predicted in pairs),
            sum(label not in gold and label in predicted for gold, predicted in pairs),
            sum(label in gold and label not in predicted for gold, predicted in pairs),
        ) | {"support": sum(label in gold for gold, _ in pairs)}
    true_positive = sum(len(gold & predicted) for gold, predicted in pairs)
    micro = _prf(
        true_positive,
        sum(len(predicted - gold) for gold, predicted in pairs),
        sum(len(gold - predicted) for gold, predicted in pairs),
    )
    return {
        "per_label": per_label,
        "micro": micro,
        "macro_f1": _ratio(sum(value["f1"] for value in per_label.values()), len(per_label)),
    }


def _multiclass(pairs: Sequence[tuple[str, str]], labels: Iterable[str]) -> dict[str, Any]:
    return {
        "accuracy": _ratio(sum(gold == predicted for gold, predicted in pairs), len(pairs)),
        "per_class": {
            label: _prf(
                sum(gold == label and predicted == label for gold, predicted in pairs),
                sum(gold != label and predicted == label for gold, predicted in pairs),
                sum(gold == label and predicted != label for gold, predicted in pairs),
            )
            | {"support": sum(gold == label for gold, _ in pairs)}
            for label in labels
        },
        "confusion_matrix": _confusion(Counter(pairs)),
    }


def extended_report(
    examples: Sequence[
        tuple[
            Mapping[str, Any],
            CanonicalGolden,
            Mapping[tuple[str, str], PairDecision],
            Mapping[str, ClaimDecision],
        ]
    ],
    threshold: float,
) -> dict[str, Any]:
    """Score the taxonomy that the production Mamay contract had to collapse or drop."""
    rhetoric_pairs: list[tuple[set[str], dict[str, float], str]] = []
    epistemic: list[tuple[str, str]] = []
    presentation: list[tuple[str, str]] = []
    for record, golden, pairs, claims in examples:
        gold = extended_rhetoric_gold(record, golden)
        for pair, labels in gold.items():
            if pair in pairs:
                rhetoric_pairs.append((labels, pairs[pair].rhetoric, pairs[pair].stance))
        for raw in record["annotations"]["claims"]:
            decision = claims.get(raw["id"])
            if decision is not None:
                epistemic.append((raw["epistemic_status"], decision.epistemic))
                presentation.append((raw["presentation"], decision.presentation))

    def predicted(scores: Mapping[str, float], stance: str, cutoff: float, gated: bool) -> set[str]:
        if gated and stance != "негативне":
            return set()
        return {label for label, value in scores.items() if value >= cutoff}

    return {
        "threshold": threshold,
        "rhetoric_ungated": _labelled_metrics(
            [
                (gold, predicted(scores, stance, threshold, False))
                for gold, scores, stance in rhetoric_pairs
            ],
            RHETORIC_CRITERIA,
        ),
        "rhetoric_gated_by_negative_stance": _labelled_metrics(
            [
                (gold, predicted(scores, stance, threshold, True))
                for gold, scores, stance in rhetoric_pairs
            ],
            RHETORIC_CRITERIA,
        ),
        "rhetoric_ungated_micro_f1_by_threshold": {
            str(cutoff): _labelled_metrics(
                [
                    (gold, predicted(scores, stance, cutoff, False))
                    for gold, scores, stance in rhetoric_pairs
                ],
                RHETORIC_CRITERIA,
            )["micro"]["f1"]
            for cutoff in SWEEP_THRESHOLDS
        },
        "epistemic": _multiclass(epistemic, EPISTEMIC_CRITERIA),
        "presentation": _multiclass(presentation, PRESENTATION_CRITERIA),
    }


def usage_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarise cost, tokens, latency, and resolved model versions."""
    responses = [response for row in rows for response in row["responses"]]
    usage = [response["body"].get("usage", {}) for response in responses]
    latencies = sorted(response["latency_seconds"] for response in responses)
    return {
        "examples": len(rows),
        "status": dict(Counter(row["status"] for row in rows)),
        "requests": len(responses),
        "questions": sum(len(response["body"]["answers"]) for response in responses),
        "input_tokens": sum(int(value.get("input_tokens", 0)) for value in usage),
        "output_tokens": sum(int(value.get("output_tokens", 0)) for value in usage),
        "cost_usd": sum(float(value.get("cost", 0.0)) for value in usage),
        "median_request_seconds": latencies[len(latencies) // 2] if latencies else 0.0,
        "resolved_models": sorted({str(response["body"].get("model")) for response in responses}),
    }


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_annotations(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def mamay_alignment(
    mamay_path: Path, annotations_path: Path
) -> dict[str, tuple[set[tuple[str, str]], set[str]]]:
    """Return the golden pairs and claims Mamay v3.5.2 produced, per example."""
    golden_by_id = {record.example_id: record for record in load_golden_jsonl(annotations_path)}
    aligned: dict[str, tuple[set[tuple[str, str]], set[str]]] = {}
    for row in load_rows(mamay_path):
        identifier = row["input"]["example_id"]
        prediction = canonical_prediction(row.get("final_output"), golden_by_id[identifier])
        if prediction is None:
            aligned[identifier] = (set(), set())
            continue
        aligned[identifier] = (
            {(item.claim_id, item.entity_id) for item in prediction.classifications},
            {claim.id for claim in prediction.claims},
        )
    return aligned


Decoded = tuple[
    CanonicalGolden, Mapping[tuple[str, str], PairDecision], Mapping[str, ClaimDecision]
]


def negative_stance_auc(decoded: Sequence[Decoded]) -> float:
    """Return how well p(негативне) ranks reviewed negative pairs above the rest."""
    positive: list[float] = []
    negative: list[float] = []
    for golden, pairs, _ in decoded:
        for item in golden.classifications:
            decision = pairs.get((item.claim_id, item.entity_id))
            if item.stance is None or decision is None:
                continue
            probability = decision.stance_probabilities.get("негативне", 0.0)
            (positive if item.stance == "негативне" else negative).append(probability)
    wins = sum(
        1.0 if high > low else 0.5 if high == low else 0.0 for high in positive for low in negative
    )
    return float(_ratio(wins, len(positive) * len(negative)))


def held_out_calibration(
    decoded: Sequence[Decoded],
    alignment: Mapping[str, tuple[set[tuple[str, str]], set[str]]],
    old55: set[str],
    extension: set[str] | None = None,
) -> dict[str, Any]:
    """Select thresholds on old55 and report them on diagnostic45, over Mamay's pairs only."""

    def report(negative: float | None, rhetoric: float) -> dict[str, dict[str, Any]]:
        items = [
            EvaluationItem(
                golden,
                production_prediction(
                    golden,
                    pairs,
                    claims,
                    rhetoric,
                    alignment[golden.example_id][0],
                    alignment[golden.example_id][1],
                    negative,
                ),
            )
            for golden, pairs, claims in decoded
            if golden.example_id in alignment
        ]
        return cast(dict[str, dict[str, Any]], benchmark_report(items, old55, extension or set()))

    negative = max(
        NEGATIVE_GRID,
        key=lambda value: report(value, DEFAULT_THRESHOLD)["old55"]["stance"]["негативне"]["f1"],
    )
    rhetoric = max(
        RHETORIC_GRID, key=lambda value: report(negative, value)["old55"]["rhetoric_micro_f1"]
    )

    def section(values: Mapping[str, Any]) -> dict[str, Any]:
        keys = ("stance", "rhetoric_per_label", "rhetoric_micro_f1", "rhetoric_macro_f1")
        return {key: values[key] for key in keys} | {
            "claim_target_attack_detection": values["claim_target_attack_detection"],
            "post_level_attack_detection": values["post_level_attack_detection"],
        }

    return {
        "selected_on": "old55",
        "evaluated_on": "diagnostic45",
        "negative_threshold": negative,
        "rhetoric_threshold": rhetoric,
        "negative_stance_auc_all_reviewed_pairs": negative_stance_auc(decoded),
        "diagnostic45_default": section(report(None, DEFAULT_THRESHOLD)["diagnostic45"]),
        "diagnostic45_calibrated": section(report(negative, rhetoric)["diagnostic45"]),
    }


def build_summary(
    rows: Sequence[Mapping[str, Any]],
    annotations: Sequence[Mapping[str, Any]],
    annotations_path: Path,
    mamay_path: Path,
    old55_path: Path,
    threshold: float,
) -> dict[str, Any]:
    """Compute the production-taxonomy, head-to-head, and extended-taxonomy reports."""
    records = {record["example_id"]: record for record in annotations}
    old55 = completed_example_ids(old55_path)
    extension = extension_example_ids(annotations_path)
    alignment = mamay_alignment(mamay_path, annotations_path) if mamay_path.exists() else {}
    full: list[EvaluationItem] = []
    on_mamay_pairs: list[EvaluationItem] = []
    extended_inputs = []
    decoded: list[Decoded] = []
    for row in rows:
        record = records[row["input"]["example_id"]]
        golden = load_golden(record)
        if row["status"] != "completed":
            full.append(EvaluationItem(golden, None, degraded=True))
            continue
        pairs, claims = decode_answers(merged_answers(row))
        full.append(EvaluationItem(golden, production_prediction(golden, pairs, claims, threshold)))
        if golden.example_id in alignment:
            allowed_pairs, allowed_claims = alignment[golden.example_id]
            on_mamay_pairs.append(
                EvaluationItem(
                    golden,
                    production_prediction(
                        golden, pairs, claims, threshold, allowed_pairs, allowed_claims
                    ),
                )
            )
        extended_inputs.append((record, golden, pairs, claims))
        decoded.append((golden, pairs, claims))
    mamay = (
        semantic_benchmark_report(mamay_path, annotations_path, old55_path)
        if mamay_path.exists()
        else None
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "note": (
            "Reviewed claims and attribution are inputs, so claim coverage and the attribution "
            "matrix are not Jev metrics. Head-to-head compares Jev with Mamay v3.5.2 on exactly "
            "the claim-target pairs and claims Mamay produced and aligned."
        ),
        "run": usage_summary(rows),
        "production_taxonomy_all_reviewed_pairs": benchmark_report(full, old55, extension),
        "head_to_head": {
            "mamay_v3_5_2": mamay,
            "jev_on_mamay_pairs": benchmark_report(on_mamay_pairs, old55, extension),
            "jev_calibrated_held_out": (
                held_out_calibration(decoded, alignment, old55, extension) if alignment else None
            ),
        },
        "extended_taxonomy": extended_report(extended_inputs, threshold),
    }


def validate_rows(
    rows: Sequence[Mapping[str, Any]], annotations: Sequence[Mapping[str, Any]]
) -> None:
    """Require one completed row per example with every question answered."""
    expected = {record["example_id"]: record for record in annotations}
    identifiers = [row["input"]["example_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)) or set(identifiers) != set(expected):
        raise ValueError("responses must contain exactly one row per golden example")
    for row in rows:
        if row["status"] != "completed":
            raise ValueError(f"{row['input']['example_id']} did not complete")
        golden = load_golden(expected[row["input"]["example_id"]])
        prompts = PROMPTS[row.get("prompt_version", "v1")]
        questions = set(build_questions(golden, entity_names(expected[golden.example_id]), prompts))
        if questions != set(merged_answers(row)):
            raise ValueError(f"{golden.example_id} is missing typed answers")


def select_examples(
    annotations: Sequence[dict[str, Any]],
    partition: str,
    old55: set[str],
    extension: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Restrict a run to a benchmark partition so prompt iteration never sees diagnostic45."""
    extension = extension or set()

    def name(example_id: str) -> str:
        if example_id in old55:
            return "old55"
        return "extension400" if example_id in extension else "diagnostic45"

    if partition == "all":
        return list(annotations)
    return [record for record in annotations if name(record["example_id"]) == partition]


def parse_args(arguments: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Jev decisions on golden_v0 claims")
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--output", type=Path, default=None, help="Defaults by prompt version")
    parser.add_argument("--prompt-version", choices=sorted(PROMPTS), default="v1")
    parser.add_argument(
        "--examples", choices=("all", "old55", "diagnostic45", "extension400"), default="all"
    )
    parser.add_argument("--mamay", type=Path, default=DEFAULT_MAMAY)
    parser.add_argument("--old55", type=Path, default=DEFAULT_OLD55)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--max-questions", type=int, default=80)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None, help="Use only the first N examples")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args(arguments)


async def run(arguments: Iterable[str] | None = None) -> None:
    """Run, validate, and summarise the resumable Jev comparison artifact."""
    args = parse_args(arguments)
    if args.output is None:
        args.output = (
            DEFAULT_OUTPUT.parents[1]
            / f"jev_vs_golden_{args.prompt_version}"
            / (DEFAULT_OUTPUT.name)
        )
    annotations = select_examples(
        load_annotations(args.annotations),
        args.examples,
        completed_example_ids(args.old55),
        extension_example_ids(args.annotations),
    )[: args.limit]
    if not args.validate_only:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY must be configured for the Jev run")
        client = OpenRouterDecisionClient(args.url, api_key)
        try:
            await generate_responses(
                annotations,
                args.output,
                client,
                setup_logging("telegram-monitor-jev-golden-v1-experiment"),
                args.model,
                args.max_questions,
                args.concurrency,
                args.prompt_version,
            )
        finally:
            await client.close()
    rows = load_rows(args.output)
    validate_rows(rows, annotations)
    summary = build_summary(
        rows, annotations, args.annotations, args.mamay, args.old55, args.threshold
    )
    args.output.with_name("summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    """Run the Jev comparison CLI."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
