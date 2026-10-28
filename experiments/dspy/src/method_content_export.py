"""Export the quality figures and the worked example of the «Як працює» system page.

The frontend shows how inference is measured without reading DVC data at runtime, so this script
writes two small JSON files under ``apps/frontend/src/content``:

* ``method-quality.json``: post x registry-entity stance metrics of the pipeline versions on the
  golden_v0 dev split and the measure-only test split. Test results are aggregates only.
* ``method-example.json``: one dev example, traced pass by pass through inference v4.9, on which
  the pipeline agrees with the reviewed annotations.

Every version is scored against the current gold (conventions, supplement and affiliations), so
older runs are comparable with the latest one. Predictions are collapsed per post and entity by
the majority of their claims, exactly as the interface counts them.

Example:
    uv run python experiments/dspy/src/method_content_export.py
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from entity_stance_report import (
    DEFAULT_ANNOTATIONS,
    DEFAULT_SEED,
    NEGATIVE,
    POSITIVE,
    PostCounts,
    StanceReport,
    bootstrap,
    f1,
    interval,
)

DATA = Path("experiments/dspy/data")
TEST_RUNS = DATA / "golden_test_v2_runs"
CONTENT = Path("apps/frontend/src/content")
# A short Ukrainian pilot100 post (partly reviewed by hand) in which the channel discredits both
# registry entities it names, ЦПК and НАБУ, and the pipeline matches the reviewed annotations.
EXAMPLE_ID = "golden_v0-011"
EXAMPLE_CHANNEL = "Times of Ukraine"
EXAMPLE_LANGUAGE = "українська"
EXAMPLE_TITLE = "Розбір допису: канал дискредитує ЦПК і НАБУ"
STANCE_KEYS = {"negative": NEGATIVE, "positive": POSITIVE}
STAGE_KEYS = {
    "1 entity not admitted": "not_admitted",
    "2 no claim about it": "no_claim",
    "3 claim, other stance": "other_stance",
    "4 correct": "correct",
}
SAMPLES = 1000


# version, dev run, test run (if scored on the measure-only split), status, what changed
VERSIONS: tuple[tuple[str, str, str | None, str, str], ...] = (
    (
        "3.6",
        "mamay_vs_golden_v3_6_all500",
        "v36",
        "previous",
        "Три проходи: сутності, твердження, оцінка.",
    ),
    (
        "3.7",
        "mamay_vs_golden_v3_7",
        "v37",
        "step",
        "Окремий прохід перевіряє, чи збіг із реєстром справді означає цю сутність.",
    ),
    (
        "4.2",
        "mamay_vs_golden_v4_2",
        "v42",
        "step",
        "Окремий прохід визначає, кого саме оцінює кожне твердження.",
    ),
    (
        "4.3",
        "mamay_vs_golden_v4_3",
        None,
        "step",
        "Твердження шукаються окремим запитом для кожної сутності реєстру.",
    ),
    (
        "4.4",
        "mamay_vs_golden_v4_4",
        None,
        "step",
        "Оцінка враховує позитивний контекст без прямої похвали.",
    ),
    (
        "4.5",
        "mamay_vs_golden_v4_5",
        None,
        "rejected",
        "Прохід цілей розділено на два запити.",
    ),
    (
        "4.6",
        "mamay_vs_golden_v4_6",
        None,
        "rejected",
        "Прохід цілей без підказки про напрям оцінки.",
    ),
    (
        "4.7",
        "mamay_vs_golden_v4_7",
        None,
        "rejected",
        "Підказку повернено зі строгим правилом для прихильників.",
    ),
    (
        "4.8",
        "mamay_vs_golden_v4_8",
        None,
        "step",
        "Критика людей переноситься на їхні організації; 812 нових аліасів.",
    ),
    (
        "4.9",
        "mamay_vs_golden_v4_9",
        "v49",
        "current",
        "Зв'язки з організаціями шукаються лише для негативно оцінених людей.",
    ),
)


def scores(counts: Mapping[str, PostCounts], draws: Sequence[float]) -> dict[str, Any]:
    """Return precision, recall, F1 with its bootstrap interval, and the summed counts."""
    precision, recall, score = f1(counts.values())
    low, high = interval(draws)
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(score, 4),
        "f1_interval": [round(low, 4), round(high, 4)],
        "tp": sum(row.tp for row in counts.values()),
        "fp": sum(row.fp for row in counts.values()),
        "fn": sum(row.fn for row in counts.values()),
    }


def compare(
    report: StanceReport, runs: Sequence[tuple[str, Path]], split: str
) -> tuple[int, list[dict[str, Any]]]:
    """Score every run on the examples all of them completed; returns the shared post count."""
    loaded = [report.rows(path, split) for _, path in runs]
    shared = set.intersection(*(set(rows) for rows in loaded))
    results: list[dict[str, Any]] = [{"version": version} for version, _ in runs]
    for key, stance in STANCE_KEYS.items():
        counts = [
            report.counts({name: rows[name] for name in shared}, stance, majority=True)
            for rows in loaded
        ]
        draws = bootstrap(counts, samples=SAMPLES)
        for index, result in enumerate(results):
            result[key] = scores(counts[index], [draw[index] for draw in draws])
    return len(shared), results


def difference(
    report: StanceReport, before: Path, after: Path, split: str
) -> dict[str, dict[str, Any]]:
    """Return the F1 change between two runs with a paired bootstrap interval."""
    first, second = report.rows(before, split), report.rows(after, split)
    shared = set(first) & set(second)
    result: dict[str, dict[str, Any]] = {}
    for key, stance in STANCE_KEYS.items():
        counts = [
            report.counts({name: rows[name] for name in shared}, stance, majority=True)
            for rows in (first, second)
        ]
        draws = bootstrap(counts, samples=SAMPLES)
        low, high = interval([draw[1] - draw[0] for draw in draws])
        change = f1(counts[1].values())[2] - f1(counts[0].values())[2]
        result[key] = {"f1": round(change, 4), "interval": [round(low, 4), round(high, 4)]}
    return result


def gold_profile(report: StanceReport, identifiers: set[str]) -> dict[str, int]:
    """Count reviewed negative and positive post x entity pairs and posts without any stance."""
    negative = positive = silent = 0
    for identifier in identifiers:
        stances = report.gold(identifier)
        negative += sum(NEGATIVE in values for values in stances.values())
        positive += sum(POSITIVE in values for values in stances.values())
        silent += not any(values & {NEGATIVE, POSITIVE} for values in stances.values())
    return {
        "posts": len(identifiers),
        "negative_pairs": negative,
        "positive_pairs": positive,
        "posts_without_stance": silent,
    }


def quality(report: StanceReport) -> dict[str, Any]:
    """Collect the dataset profile, the dev history and the measure-only test comparison."""
    test_ids = report.test_ids
    dev_ids = set(report.golden) - test_ids
    dev_posts, history = compare(
        report,
        [(version, DATA / run / "comparisons.jsonl") for version, run, *_ in VERSIONS],
        "dev",
    )
    for result, (_, _, _, status, note) in zip(history, VERSIONS, strict=True):
        result.update(status=status, note=note)
    tested = [
        (version, TEST_RUNS / run / "comparisons.jsonl") for version, _, run, *_ in VERSIONS if run
    ]
    test_posts, test = compare(report, tested, "test")
    latest = report.rows(TEST_RUNS / "v49" / "comparisons.jsonl", "test")
    stages = {
        key: {
            STAGE_KEYS[stage]: count
            for stage, count in sorted(report.stages(latest, stance, majority=True).items())
        }
        for key, stance in STANCE_KEYS.items()
    }
    return {
        "unit": "допис × сутність реєстру",
        "dataset": {
            "posts": len(report.golden),
            "dev": gold_profile(report, dev_ids),
            "test": gold_profile(report, test_ids),
        },
        "dev": {"shared_posts": dev_posts, "versions": history},
        "test": {
            "shared_posts": test_posts,
            "versions": test,
            "change": difference(
                report,
                TEST_RUNS / "v36" / "comparisons.jsonl",
                TEST_RUNS / "v49" / "comparisons.jsonl",
                "test",
            ),
            "stages": stages,
        },
    }


def spans(text: str, forms: Sequence[str]) -> list[dict[str, int]]:
    """Return non-overlapping character spans of every occurrence of the given forms."""
    found: list[tuple[int, int]] = []
    for form in sorted(set(forms), key=len, reverse=True):
        for match in re.finditer(re.escape(form), text):
            if all(match.end() <= start or match.start() >= end for start, end in found):
                found.append((match.start(), match.end()))
    return [{"start": start, "end": end} for start, end in sorted(found)]


def example(report: StanceReport, path: Path, identifier: str) -> dict[str, Any]:
    """Trace one dev example through every pass of a comparison run."""
    if identifier in report.test_ids:
        raise ValueError("the worked example must come from the dev split")
    row = report.rows(path, "dev")[identifier]
    text = row["input"]["post_text"]
    final = row["final_output"]
    passes: dict[str, list[Any]] = {}
    for attempt in row["attempts"]:
        passes.setdefault(attempt["pass"], []).append(attempt["sanitized_payload"])
    monitored = [entity for entity in final["entities"] if entity.get("monitored")]
    return {
        "example_id": identifier,
        "channel": EXAMPLE_CHANNEL,
        "language": EXAMPLE_LANGUAGE,
        "title": EXAMPLE_TITLE,
        "pipeline_version": row["run_metadata"]["pipeline_version"],
        "model": row["run_metadata"]["model"],
        "text": text,
        "registry_matches": [
            {
                "entity_id": entity["id"],
                "canonical_name": entity["canonical_name"],
                "spans": spans(text, entity["mentions"]),
            }
            for entity in monitored
        ],
        "passes": passes,
        "final": {key: final[key] for key in ("entities", "claims", "classifications")},
        "gold": {name: sorted(values) for name, values in sorted(report.gold(identifier).items())},
    }


def write(path: Path, payload: Mapping[str, Any]) -> None:
    """Write one content file in the committed format."""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(arguments: Sequence[str] | None = None) -> None:
    """Write method-quality.json and method-example.json."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--content", type=Path, default=CONTENT)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--registry-seed", type=Path, default=DEFAULT_SEED)
    args = parser.parse_args(arguments)
    report = StanceReport(args.annotations, args.registry_seed)
    write(args.content / "method-quality.json", quality(report))
    write(
        args.content / "method-example.json",
        example(report, DATA / "mamay_vs_golden_v4_9" / "comparisons.jsonl", EXAMPLE_ID),
    )


if __name__ == "__main__":
    main()
