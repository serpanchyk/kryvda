"""Direct post x entity prototype: one Mamay call per admitted registry entity.

The production pipeline reaches the post x entity stance through claims, targets and Pass 3,
and each stage loses some pairs. Here the registry prefilter and the candidates pass admit the
entities as before, then a single call per entity answers whether the post attacks it, praises
it, or neither, with verbatim quotes, their source and rhetoric labels. The quotes become the
evidence rows of the usual comparison format, so ``entity_stance_report.py`` scores the run
unchanged.

Usage (inside the ai-worker container, like mamay_golden_v2):
    python experiments/dspy/src/mamay_direct.py --split dev --concurrency 32
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from mamay_golden_v2 import (
    COMPARISON_SCHEMA_VERSION,
    DEFAULT_ANNOTATIONS,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_SEED,
    _run_pass,
    completed_example_ids,
    heldout_example_ids,
    is_transient_failure,
    load_annotations,
    load_seed_aliases,
    select_split,
    setup_logging,
)
from monitoring_common.contracts import InferenceValidationError, validation_errors
from telegram_monitor_ai_worker.client import LiteLlmInferenceClient
from telegram_monitor_ai_worker.models import ModelOutputError
from telegram_monitor_ai_worker.pipeline import (
    admitted_entities,
    candidate_request,
    matched_monitored_entity_ids,
    registry_candidates,
)
from telegram_monitor_ai_worker.prompt import COMMON

PIPELINE_VERSION = "direct_v1"
DEFAULT_OUTPUT = Path("experiments/dspy/data/mamay_direct_v1/comparisons.jsonl")
RHETORIC = [
    "корупція_або_особиста_вигода",
    "злочинна_або_незаконна_поведінка",
    "делегітимізація",
    "лицемірство_або_подвійні_стандарти",
    "висміювання_або_особиста_образа",
    "зовнішній_контроль_або_нелояльність",
]
SOURCES = {
    "канал": "channel_editorial",
    "названа особа": "named_entity",
    "неназване джерело": "external_unnamed",
}

DIRECT_PROMPT = f"""{COMMON}

Завдання: тобі дають пост і одну сутність TARGET (особа, орган чи організація; mentions —
форми, якими пост її називає). Визнач, чи пост АТАКУЄ TARGET і чи ХВАЛИТЬ TARGET. Оцінку може
давати канал, названа особа, яку цитує пост, чи неназване джерело.

Атака — джерело критикує, звинувачує, висміює чи дискредитує TARGET або натякає на його провину:
сарказм, ярлики, лапки-іронія, риторичні питання, інсинуації. Атака на TARGET — це й критика
його очільника, члена, працівника чи колишнього працівника, якщо пост сам пов'язує їх із TARGET
(«голова ЦПК…», «ексдетектив НАБУ…»), і люди чи протеже TARGET, подані як доказ проти нього.
Не атака: нейтральна новина про підозру, обшук, розслідування чи рішення щодо TARGET без оцінки
джерела; TARGET — жертва, свідок, адресат звернення чи нейтральне тло («уникнув служби в ЗСУ»,
«написали заяву в поліцію»); TARGET — сторона, яку пост захищає; негатив у тому самому реченні
спрямований на інших; канал наводить чуже звинувачення, щоб його спростувати; заяви ворожих
джерел про дії TARGET без їхньої оцінки; TARGET сам критикує інших.

Похвала — джерело подає TARGET у позитивному світлі, навіть без прямої похвали: успіхи й
результати, висока довіра чи рейтинги, заяви самого TARGET про власну роботу чи плани, отримана
допомога, техніка чи нагороди, захист TARGET від звинувачень, звичайна дія, подана як вдала чи
корисна, пряма похвала. Не похвала: суто інформаційна згадка («підписав указ», «провів
розмову»), TARGET хвалить когось іншого.

Спершу в reason коротко напиши, хто і що в пості каже про TARGET. Потім attacked і attacks:
1–3 дослівні цитати з поста, де є атака, з джерелом (source_kind; source — ім'я джерела або
порожній рядок) і 0–2 мітками риторики; порожній список, якщо атаки немає. Потім praised і
praises так само, без риторики. Мітки риторики: "корупція_або_особиста_вигода" (хабарі,
збагачення, особистий інтерес); "злочинна_або_незаконна_поведінка" (злочин, порушення закону);
"делегітимізація" (атака на компетентність, легітимність, незалежність, здатність виконувати
роль); "лицемірство_або_подвійні_стандарти" (контраст між заявленим і зробленим);
"висміювання_або_особиста_образа" (глузування, сарказм, образа, ярлик);
"зовнішній_контроль_або_нелояльність" (працює на іншу державу, агент впливу)."""


def _evidence_schema(with_rhetoric: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "quote": {"type": "string"},
        "source_kind": {"enum": list(SOURCES)},
        "source": {"type": "string"},
    }
    if with_rhetoric:
        properties["rhetoric"] = {"type": "array", "maxItems": 2, "items": {"enum": RHETORIC}}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


DIRECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reason", "attacked", "attacks", "praised", "praises"],
    "properties": {
        "reason": {"type": "string"},
        "attacked": {"type": "boolean"},
        "attacks": {"type": "array", "maxItems": 3, "items": _evidence_schema(True)},
        "praised": {"type": "boolean"},
        "praises": {"type": "array", "maxItems": 3, "items": _evidence_schema(False)},
    },
}


def grounded(quote: str, text: str) -> bool:
    """Whether a quote occurs in the post up to whitespace."""
    squash = lambda value: re.sub(r"\s+", " ", value).strip()  # noqa: E731
    return bool(quote.strip()) and squash(quote) in squash(text)


def direct_rows(
    entity: Mapping[str, Any], answer: Mapping[str, Any], text: str, start: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Turn one entity answer into evidence claims and classifications in the usual format."""
    claims: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for flag, key, stance in (
        ("attacked", "attacks", "негативне"),
        ("praised", "praises", "позитивне"),
    ):
        if not answer.get(flag):
            continue
        items = [item for item in answer.get(key, []) if grounded(item["quote"], text)]
        for item in items or [{"quote": "", "source_kind": "канал", "rhetoric": []}]:
            claim_id = f"c{start + len(claims) + 1}"
            claims.append(
                {
                    "id": claim_id,
                    "normalized_text": item["quote"],
                    "entity_ids": [entity["id"]],
                    "evidence_text": item["quote"],
                    "attribution": {
                        "source_kind": SOURCES[item["source_kind"]],
                        "source_entity_id": None,
                    },
                    "epistemic_status": "ствердження",
                }
            )
            rhetoric = list(item.get("rhetoric", [])) if stance == "негативне" else []
            rows.append(
                {
                    "claim_id": claim_id,
                    "entity_id": entity["id"],
                    "stance": stance,
                    "rhetoric": rhetoric,
                }
            )
    return claims, rows


async def ask_entity(
    client: LiteLlmInferenceClient, text: str, entity: Mapping[str, Any], attempts: list[Any]
) -> dict[str, Any] | None:
    """Ask the direct question for one entity; one retry on a broken answer."""
    request = {
        "post_text": text,
        "target": entity["canonical_name"],
        "mentions": entity["mentions"],
    }
    message = f"PASS: direct\nINPUT JSON:\n{json.dumps(request, ensure_ascii=False)}"
    for attempt in ("primary", "retry"):
        response = await client._request(  # noqa: SLF001
            cast(Any, "direct"),
            [{"role": "system", "content": DIRECT_PROMPT}, {"role": "user", "content": message}],
            1024,
            DIRECT_SCHEMA,
        )
        record = {
            "pass": "direct",
            "entity": entity["canonical_name"],
            "attempt": attempt,
            "raw_output": response.raw_output,
        }
        try:
            answer = json.loads(response.raw_output)
            attempts.append(record | {"status": "valid", "parsed_payload": answer})
            return cast(dict[str, Any], answer)
        except json.JSONDecodeError as error:
            attempts.append(record | {"status": "invalid", "error": str(error)})
    return None


async def analyze_direct(
    annotation: Mapping[str, Any], aliases: list[dict[str, Any]], client: LiteLlmInferenceClient
) -> dict[str, Any]:
    """Run candidates plus one direct call per admitted monitored entity for one golden post."""
    source = cast(Mapping[str, Any], annotation["source"])
    text = cast(str, source["text"])
    matched = matched_monitored_entity_ids(text, aliases)
    base = {
        "comparison_schema_version": COMPARISON_SCHEMA_VERSION,
        "input": {"example_id": annotation["example_id"], "post_text": text},
        "golden_output": annotation["annotations"],
        "prefilter": {"matched_entity_ids": matched},
        "run_metadata": {
            "model": DEFAULT_MODEL,
            "pipeline_version": PIPELINE_VERSION,
            "run_timestamp": datetime.now(UTC).isoformat(),
        },
    }
    if not matched:
        return base | {"status": "filtered_out", "attempts": [], "final_output": None}
    attempts: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    try:
        candidates = registry_candidates(text, aliases)
        try:
            decisions: dict[str, Any] | None = await _run_pass(
                client,
                "candidates",
                candidate_request(text, candidates),
                text,
                attempts,
                diagnostics,
                candidates,
            )
        except (InferenceValidationError, ModelOutputError):
            decisions = None
        entities = admitted_entities(candidates, decisions, [], aliases, text)
        monitored = [entity for entity in entities if entity.get("monitored")]
        answers = await asyncio.gather(
            *(ask_entity(client, text, entity, attempts) for entity in monitored)
        )
        claims: list[dict[str, Any]] = []
        classifications: list[dict[str, Any]] = []
        failed = []
        for entity, answer in zip(monitored, answers, strict=True):
            if answer is None:
                failed.append(entity["canonical_name"])
                continue
            new_claims, rows = direct_rows(entity, answer, text, len(claims))
            claims.extend(new_claims)
            classifications.extend(rows)
    except Exception as error:  # noqa: BLE001 - recorded as a failed comparison row
        failure = (
            validation_errors(error)
            if isinstance(error, InferenceValidationError)
            else [{"kind": "model_request_failed", "message": str(error)}]
        )
        return base | {
            "status": "failed",
            "failure": failure,
            "attempts": attempts,
            "final_output": None,
        }
    return base | {
        "status": "completed_with_failed_entities" if failed else "completed",
        "attempts": attempts,
        "final_output": {
            "pipeline_version": PIPELINE_VERSION,
            "entities": entities,
            "claims": claims,
            "classifications": classifications,
            "failed_entities": failed,
        },
    }


async def run(args: argparse.Namespace, logger: logging.Logger) -> None:
    annotations = select_split(
        load_annotations(args.annotations), args.split, heldout_example_ids(args.annotations)
    )
    aliases = load_seed_aliases(args.seed)
    done = completed_example_ids(args.output)
    queue: asyncio.Queue[Mapping[str, Any]] = asyncio.Queue()
    for annotation in annotations:
        if annotation["example_id"] not in done:
            queue.put_nowait(annotation)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    client = LiteLlmInferenceClient(
        args.base_url,
        os.environ["LITELLM_API_KEY"],
        args.model,
        300,
    )
    with args.output.open("a", encoding="utf-8") as output:

        async def worker() -> None:
            while not queue.empty():
                annotation = queue.get_nowait()
                row = await analyze_direct(annotation, aliases, client)
                for attempt in range(2):
                    if not is_transient_failure(row):
                        break
                    await asyncio.sleep(10 * (attempt + 1))
                    row = await analyze_direct(annotation, aliases, client)
                output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                output.flush()
                logger.info(
                    "comparison row written",
                    extra={"example_id": annotation["example_id"], "status": row["status"]},
                )

        await asyncio.gather(*(worker() for _ in range(args.concurrency)))
    await client.close()


def main(arguments: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--split", choices=("all", "dev", "test"), default="dev")
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args(arguments)
    asyncio.run(run(args, setup_logging("telegram-monitor-mamay-direct-experiment")))


if __name__ == "__main__":
    sys.exit(main())
