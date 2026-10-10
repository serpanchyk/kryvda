"""Replace only Mamay's Pass 3 with Jev typed decisions on Mamay's own extracted claims.

Unlike `jev_golden_v1.py`, Jev receives the entities, claims, attribution, and evidence produced by
the recorded Mamay inference run, so both variants classify the same imperfect extraction. Both
outputs pass through the same canonical alignment and semantic report, which makes the comparison
end to end: variant A is Mamay alone, variant B swaps in Jev for claim-target classification, and
variant B+E also takes Jev's epistemic status where it maps onto the production labels.
"""

import argparse
import asyncio
import copy
import json
import logging
import os
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
from golden_report import (
    EvaluationItem,
    benchmark_report,
    canonical_prediction,
    extension_example_ids,
)
from golden_schema import (
    EPISTEMIC_MAP,
    CanonicalGolden,
    GoldenClaim,
    GoldenClassification,
    GoldenEntity,
    load_golden,
)
from jev_golden_v1 import (
    DEFAULT_ANNOTATIONS,
    DEFAULT_MODEL,
    DEFAULT_OLD55,
    DEFAULT_THRESHOLD,
    DEFAULT_URL,
    PROMPTS,
    ClaimDecision,
    DecisionClient,
    OpenRouterDecisionClient,
    PairDecision,
    build_questions,
    build_requests,
    decode_answers,
    load_annotations,
    load_rows,
    merged_answers,
    production_rhetoric,
    usage_summary,
)
from mamay_golden_v2 import completed_example_ids
from monitoring_common.logging import setup_logging

SCHEMA_VERSION = "jev_hybrid_v1"
DEFAULT_MAMAY = Path("experiments/dspy/data/mamay_vs_golden_v3_6/comparisons.jsonl")
DEFAULT_OUTPUT = Path("experiments/dspy/data/jev_hybrid_v3_6/responses.jsonl")
DEFAULT_PROMPT_VERSION = "v4"


def mamay_claim_set(
    final_output: Mapping[str, Any], source_text: str, example_id: str
) -> tuple[CanonicalGolden, dict[str, str]]:
    """Expose Mamay's extraction as the claim set that Jev classifies.

    The expected pairs follow production: every monitored entity participating in a claim.
    """
    entities = [
        GoldenEntity(
            id=entity["id"],
            registry_entity_id=entity.get("registry_entity_id"),
            canonical_name=entity.get("canonical_name"),
            monitored=bool(entity["monitored"]),
        )
        for entity in final_output["entities"]
    ]
    names = {
        entity["id"]: entity.get("canonical_name") or entity["mentions"][0]
        for entity in final_output["entities"]
    }
    claims = [
        GoldenClaim(
            id=claim["id"],
            normalized_text=claim["normalized_text"],
            entity_ids=list(claim["entity_ids"]),
            evidence_text=claim["evidence_text"],
            attribution={
                "source_kind": claim["attribution"]["source_kind"],
                "source_entity_id": claim["attribution"].get("source_entity_id"),
            },
            epistemic_status=claim["epistemic_status"],
            evidence_start=claim.get("evidence_start"),
            evidence_end=claim.get("evidence_end"),
        )
        for claim in final_output["claims"]
    ]
    monitored = {entity.id for entity in entities if entity.monitored}
    pairs = [
        GoldenClassification(claim.id, entity_id, None, [])
        for claim in claims
        for entity_id in claim.entity_ids
        if entity_id in monitored
    ]
    claim_set = CanonicalGolden(
        example_id=example_id,
        source_text=source_text,
        entities=entities,
        claims=claims,
        classifications=pairs,
        original_schema_version=str(final_output.get("pipeline_version", "")),
    )
    return claim_set, names


def hybrid_output(
    final_output: Mapping[str, Any],
    pairs: Mapping[tuple[str, str], PairDecision],
    claims: Mapping[str, ClaimDecision],
    threshold: float = DEFAULT_THRESHOLD,
    replace_epistemic: bool = False,
) -> dict[str, Any]:
    """Return Mamay's final output with Jev classifications and, optionally, epistemic status."""
    output = copy.deepcopy(dict(final_output))
    classifications = []
    for (claim_id, entity_id), decision in sorted(pairs.items()):
        classifications.append(
            {
                "claim_id": claim_id,
                "entity_id": entity_id,
                "stance": decision.stance,
                "rhetoric": production_rhetoric(decision, threshold),
            }
        )
    output["classifications"] = classifications
    if replace_epistemic:
        for claim in output["claims"]:
            decision = claims.get(claim["id"])
            mapped = EPISTEMIC_MAP.get(decision.epistemic) if decision is not None else None
            if mapped is not None:
                claim["epistemic_status"] = mapped
    return output


def with_mamay_stance(
    final_output: Mapping[str, Any], pairs: Mapping[tuple[str, str], PairDecision]
) -> dict[tuple[str, str], PairDecision]:
    """Keep Mamay's stance and Jev's rhetoric, which v4 asks for every pair."""
    stances = {
        (item["claim_id"], item["entity_id"]): item["stance"]
        for item in final_output["classifications"]
    }
    return {
        pair: replace(decision, stance=stances.get(pair, decision.stance))
        for pair, decision in pairs.items()
    }


async def analyze_row(
    mamay_row: Mapping[str, Any],
    source_text: str,
    client: DecisionClient,
    model: str,
    max_questions: int,
    prompt_version: str,
) -> dict[str, Any]:
    """Classify one Mamay extraction with Jev and keep every raw request and response."""
    identifier = mamay_row["input"]["example_id"]
    claim_set, names = mamay_claim_set(mamay_row["final_output"], source_text, identifier)
    requests = build_requests(claim_set, names, model, max_questions, PROMPTS[prompt_version])
    responses: list[dict[str, Any]] = []
    row: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "input": {"example_id": identifier},
        "prompt_version": prompt_version,
        "mamay_pipeline_version": mamay_row["final_output"].get("pipeline_version"),
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
    mamay_rows: Sequence[Mapping[str, Any]],
    sources: Mapping[str, str],
    output_path: Path,
    client: DecisionClient,
    logger: logging.Logger,
    model: str = DEFAULT_MODEL,
    max_questions: int = 80,
    concurrency: int = 4,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> tuple[int, int]:
    """Append missing rows for every Mamay example with a final output."""
    if concurrency < 1:
        raise ValueError("concurrency must be at least one")
    completed = completed_example_ids(output_path)
    pending = [
        row
        for row in mamay_rows
        if row.get("final_output") is not None and row["input"]["example_id"] not in completed
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    failed = 0

    async def process(mamay_row: Mapping[str, Any]) -> None:
        nonlocal failed
        identifier = mamay_row["input"]["example_id"]
        async with semaphore:
            row = await analyze_row(
                mamay_row, sources[identifier], client, model, max_questions, prompt_version
            )
        async with lock:
            with output_path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
            failed += row["status"] != "completed"
            logger.info(
                "jev_hybrid_example_written",
                extra={"example_id": identifier, "status": row["status"]},
            )

    await asyncio.gather(*(process(row) for row in pending))
    return len(pending), failed


def validate_rows(
    rows: Sequence[Mapping[str, Any]],
    mamay_rows: Sequence[Mapping[str, Any]],
    sources: Mapping[str, str],
) -> None:
    """Require one completed row, answering every question, per Mamay final output."""
    expected = {
        row["input"]["example_id"]: row for row in mamay_rows if row.get("final_output") is not None
    }
    identifiers = [row["input"]["example_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)) or set(identifiers) != set(expected):
        raise ValueError("responses must contain exactly one row per Mamay final output")
    for row in rows:
        identifier = row["input"]["example_id"]
        if row["status"] != "completed":
            raise ValueError(f"{identifier} did not complete")
        claim_set, names = mamay_claim_set(
            expected[identifier]["final_output"], sources[identifier], identifier
        )
        questions = build_questions(claim_set, names, PROMPTS[row["prompt_version"]])
        if set(questions) != set(merged_answers(row)):
            raise ValueError(f"{identifier} is missing typed answers")


def stance_agreement(
    mamay_rows: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Count how often Jev and Mamay agree on the stance of the same extracted pair."""
    decided = {row["input"]["example_id"]: decode_answers(merged_answers(row))[0] for row in rows}
    counts: Counter[tuple[str, str]] = Counter()
    for mamay_row in mamay_rows:
        pairs = decided.get(mamay_row["input"]["example_id"])
        if pairs is None or mamay_row.get("final_output") is None:
            continue
        for item in mamay_row["final_output"]["classifications"]:
            decision = pairs.get((item["claim_id"], item["entity_id"]))
            if decision is not None:
                counts[(item["stance"], decision.stance)] += 1
    total = sum(counts.values())
    matrix: dict[str, dict[str, int]] = {}
    for (mamay, jev), count in sorted(counts.items()):
        matrix.setdefault(mamay, {})[jev] = count
    return {
        "pairs": total,
        "agreement": sum(count for (mamay, jev), count in counts.items() if mamay == jev) / total
        if total
        else 0.0,
        "mamay_rows_jev_columns": matrix,
    }


def build_summary(
    rows: Sequence[Mapping[str, Any]],
    mamay_rows: Sequence[Mapping[str, Any]],
    annotations: Sequence[Mapping[str, Any]],
    annotations_path: Path,
    old55_path: Path,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Score Mamay alone and both hybrid variants through one canonical evaluation path."""
    records = {record["example_id"]: record for record in annotations}
    old55 = completed_example_ids(old55_path)
    extension = extension_example_ids(annotations_path)
    decided = {
        row["input"]["example_id"]: decode_answers(merged_answers(row))
        for row in rows
        if row["status"] == "completed"
    }
    names = ("hybrid", "hybrid_epistemic", "mamay_stance_jev_rhetoric")
    variants: dict[str, list[EvaluationItem]] = {"mamay": [], **{name: [] for name in names}}
    for mamay_row in mamay_rows:
        identifier = mamay_row["input"]["example_id"]
        golden = load_golden(records[identifier])
        final_output = mamay_row.get("final_output")
        degraded = mamay_row.get("status") != "completed"
        variants["mamay"].append(
            EvaluationItem(golden, canonical_prediction(final_output, golden), degraded)
        )
        if final_output is None or identifier not in decided:
            for name in names:
                variants[name].append(EvaluationItem(golden, None, True))
            continue
        pairs, claims = decided[identifier]
        outputs = {
            "hybrid": hybrid_output(final_output, pairs, claims, threshold),
            "hybrid_epistemic": hybrid_output(final_output, pairs, claims, threshold, True),
            "mamay_stance_jev_rhetoric": hybrid_output(
                final_output, with_mamay_stance(final_output, pairs), claims, threshold
            ),
        }
        for name, output in outputs.items():
            variants[name].append(
                EvaluationItem(golden, canonical_prediction(output, golden), degraded)
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "note": (
            "Every variant classifies Mamay's own extraction and is aligned to golden_v0 by the "
            "same canonical adapter; only Pass 3 (and, in hybrid_epistemic, the epistemic field) "
            "differs. Prompts were tuned on old55 in jev_golden_v1, so diagnostic45 is held out "
            "for Jev."
        ),
        "run": usage_summary(rows),
        "mamay_v3_6": benchmark_report(variants["mamay"], old55, extension),
        "hybrid_jev_pass3": benchmark_report(variants["hybrid"], old55, extension),
        "hybrid_jev_pass3_and_epistemic": benchmark_report(
            variants["hybrid_epistemic"], old55, extension
        ),
        "mamay_stance_and_jev_rhetoric": benchmark_report(
            variants["mamay_stance_jev_rhetoric"], old55, extension
        ),
        "stance_agreement_on_mamay_pairs": stance_agreement(mamay_rows, rows),
    }


def parse_args(arguments: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Swap Mamay's Pass 3 for Jev typed decisions")
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--mamay", type=Path, default=DEFAULT_MAMAY)
    parser.add_argument("--old55", type=Path, default=DEFAULT_OLD55)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prompt-version", choices=sorted(PROMPTS), default=DEFAULT_PROMPT_VERSION)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--max-questions", type=int, default=80)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args(arguments)


async def run(arguments: Iterable[str] | None = None) -> None:
    """Run, validate, and summarise the resumable hybrid comparison."""
    args = parse_args(arguments)
    mamay_rows = load_rows(args.mamay)
    identifiers = {row["input"]["example_id"] for row in mamay_rows}
    annotations = [
        record
        for record in load_annotations(args.annotations)
        if record["example_id"] in identifiers
    ]
    sources = {record["example_id"]: load_golden(record).source_text for record in annotations}
    if not args.validate_only:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY must be configured for the Jev run")
        client = OpenRouterDecisionClient(args.url, api_key)
        try:
            await generate_responses(
                mamay_rows,
                sources,
                args.output,
                client,
                setup_logging("telegram-monitor-jev-hybrid-v1-experiment"),
                args.model,
                args.max_questions,
                args.concurrency,
                args.prompt_version,
            )
        finally:
            await client.close()
    rows = load_rows(args.output)
    validate_rows(rows, mamay_rows, sources)
    summary = build_summary(
        rows, mamay_rows, annotations, args.annotations, args.old55, args.threshold
    )
    args.output.with_name("summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    """Run the hybrid comparison CLI."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
