"""Post x registry-entity stance metrics for Mamay golden comparison runs.

Production analytics aggregate every predicted classification by monitored registry entity, so
this report scores the same unit: for each post and registry entity, whether any classification
is negative (or positive), against the reviewed annotations mapped to the registry through its
approved aliases. Error listings are allowed only on dev examples: the measure-only test split
(`golden_v0/test_split.json`) is never inspected example by example.

Examples:
    uv run python experiments/dspy/src/entity_stance_report.py report \
        v4.2=experiments/dspy/data/mamay_vs_golden_v4_2/comparisons.jsonl \
        v4.3=experiments/dspy/data/mamay_vs_golden_v4_3/comparisons.jsonl --split dev
    uv run python experiments/dspy/src/entity_stance_report.py errors \
        v4.3=experiments/dspy/data/mamay_vs_golden_v4_3/comparisons.jsonl --kind FN-neg
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from golden_report import heldout_example_ids
from golden_schema import CanonicalGolden, load_golden_jsonl

DEFAULT_ANNOTATIONS = Path("experiments/datasets/golden_v0/data/annotations.jsonl")
DEFAULT_SEED = Path("infra/postgres/init/003_registry_seed.sql")
AFFILIATIONS_FILE = "affiliations.jsonl"
NEGATIVE, POSITIVE = "негативне", "позитивне"
STANCES = {"neg": NEGATIVE, "pos": POSITIVE}
# Reviewed annotations spell a few registry names differently from every approved alias.
SPELLING_VARIANTS = {"дарія": "дар'я"}


class MeasureOnlySplitError(ValueError):
    """Raised when individual results of the measure-only test split are requested."""


@dataclass(frozen=True)
class PostCounts:
    """True/false positive and false negative counts of one post for one stance."""

    tp: int = 0
    fp: int = 0
    fn: int = 0


def normalize_name(value: str) -> str:
    """Fold case, apostrophe variants and known spelling variants of an entity name."""
    folded = value.casefold().replace("’", "'").replace("ʼ", "'")
    for variant, canonical in SPELLING_VARIANTS.items():
        folded = folded.replace(variant, canonical)
    return " ".join(folded.split())


def registry_names(aliases: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Map normalized aliases and canonical names to registry canonical names."""
    names: dict[str, str] = {}
    for row in aliases:
        canonical = str(row["canonical_name"])
        names[normalize_name(canonical)] = canonical
        names[normalize_name(str(row["alias"]))] = canonical
    return names


def golden_stances(golden: CanonicalGolden, names: Mapping[str, str]) -> dict[str, set[str]]:
    """Return the stance set of every monitored golden entity that maps to the registry."""
    by_id = {
        entity.id: names.get(normalize_name(entity.canonical_name))
        for entity in golden.entities
        if entity.monitored and entity.canonical_name
    }
    stances: dict[str, set[str]] = {name: set() for name in by_id.values() if name}
    for classification in golden.classifications:
        name = by_id.get(classification.entity_id)
        if name and classification.stance:
            stances[name].add(classification.stance)
    return stances


def predicted_stances(row: Mapping[str, Any]) -> dict[str, list[tuple[str, str, str]]]:
    """Return (stance, source kind, evidence) of every classification by registry entity."""
    output = row.get("final_output") or {}
    names = {
        entity["id"]: entity.get("canonical_name")
        for entity in output.get("entities", [])
        if entity.get("monitored") and entity.get("canonical_name")
    }
    claims = {claim["id"]: claim for claim in output.get("claims", [])}
    predicted: dict[str, list[tuple[str, str, str]]] = {name: [] for name in names.values()}
    for classification in output.get("classifications", []):
        name = names.get(classification["entity_id"])
        if name:
            claim = claims.get(classification["claim_id"], {})
            predicted[name].append(
                (
                    classification["stance"],
                    str(claim.get("attribution", {}).get("source_kind", "")),
                    str(claim.get("evidence_text", "")),
                )
            )
    return predicted


def post_counts(
    golden: Mapping[str, set[str]], predicted: Mapping[str, list[tuple[str, str, str]]], stance: str
) -> PostCounts:
    """Count one post's registry entities for one stance."""
    tp = fp = fn = 0
    for name in set(golden) | set(predicted):
        gold = stance in golden.get(name, set())
        pred = any(value == stance for value, _, _ in predicted.get(name, []))
        tp += gold and pred
        fp += pred and not gold
        fn += gold and not pred
    return PostCounts(tp, fp, fn)


def f1(counts: Iterable[PostCounts]) -> tuple[float, float, float]:
    """Return precision, recall and F1 of summed counts."""
    rows = list(counts)
    tp, fp, fn = (sum(getattr(row, field) for row in rows) for field in ("tp", "fp", "fn"))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, score


def bootstrap(
    runs: Sequence[Mapping[str, PostCounts]], samples: int = 2000, seed: int = 0
) -> list[list[float]]:
    """Resample shared posts and return the F1 of every run for every resample."""
    identifiers = sorted(set.intersection(*(set(run) for run in runs)))
    generator = random.Random(seed)
    results: list[list[float]] = []
    for _ in range(samples):
        draw = [generator.choice(identifiers) for _ in identifiers]
        results.append([f1(run[name] for name in draw)[2] for run in runs])
    return results


def interval(values: Sequence[float]) -> tuple[float, float]:
    """Return the 2.5th and 97.5th percentiles."""
    ordered = sorted(values)
    return ordered[int(0.025 * len(ordered))], ordered[int(0.975 * len(ordered)) - 1]


def loss_stage(name: str, stance: str, row: Mapping[str, Any], predicted: Mapping[str, Any]) -> str:
    """Name the pipeline stage where one reviewed (post, entity, stance) was lost."""
    output = row.get("final_output") or {}
    ids = {
        entity["id"]: entity.get("canonical_name")
        for entity in output.get("entities", [])
        if entity.get("monitored")
    }
    claimed = {
        ids[entity_id]
        for claim in output.get("claims", [])
        for entity_id in claim.get("entity_ids", [])
        if entity_id in ids
    }
    if name not in ids.values():
        return "1 entity not admitted"
    if name not in claimed:
        return "2 no claim about it"
    if not any(value == stance for value, _, _ in predicted.get(name, [])):
        return "3 claim, other stance"
    return "4 correct"


class StanceReport:
    """Score comparison runs against golden_v0 with the registry mapping applied."""

    def __init__(self, annotations: Path, seed: Path) -> None:
        from mamay_golden_v2 import load_seed_aliases

        self.golden = {record.example_id: record for record in load_golden_jsonl(annotations)}
        self.names = registry_names(load_seed_aliases(seed))
        self.test_ids = heldout_example_ids(annotations)
        self.affiliations: dict[str, set[str]] = {}
        affiliations = annotations.parent / AFFILIATIONS_FILE
        if affiliations.exists():
            for line in affiliations.read_text(encoding="utf-8").splitlines():
                link = json.loads(line)
                self.affiliations.setdefault(link["example_id"], set()).update(
                    link["organizations"]
                )

    def gold(self, identifier: str) -> dict[str, set[str]]:
        """Return reviewed stances, with criticism of a linked person carried to the organization.

        ``affiliations.jsonl`` lists, per post, the registry organizations the post links a
        negatively evaluated person to; those organizations count as negative too.
        """
        stances = golden_stances(self.golden[identifier], self.names)
        for organization in self.affiliations.get(identifier, set()):
            stances.setdefault(organization, set()).add(NEGATIVE)
        return stances

    def rows(self, path: Path, split: str) -> dict[str, dict[str, Any]]:
        """Load completed rows of one split, keyed by example ID."""
        rows: dict[str, dict[str, Any]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            identifier = row["input"]["example_id"]
            in_test = identifier in self.test_ids
            if row.get("status") == "failed" or (split == "dev" and in_test):
                continue
            if split == "test" and not in_test:
                continue
            rows[identifier] = row
        return rows

    def counts(self, rows: Mapping[str, Mapping[str, Any]], stance: str) -> dict[str, PostCounts]:
        """Return per-post counts of one stance."""
        return {
            identifier: post_counts(self.gold(identifier), predicted_stances(row), stance)
            for identifier, row in rows.items()
        }

    def stages(self, rows: Mapping[str, Mapping[str, Any]], stance: str) -> Counter[str]:
        """Count where reviewed (post, entity) pairs of one stance were found or lost."""
        stages: Counter[str] = Counter()
        for identifier, row in rows.items():
            predicted = predicted_stances(row)
            for name, values in self.gold(identifier).items():
                if stance in values:
                    stages[loss_stage(name, stance, row, predicted)] += 1
        return stages

    def errors(
        self, rows: Mapping[str, Mapping[str, Any]], kind: str
    ) -> list[tuple[str, str, list[str], list[tuple[str, str, str]]]]:
        """List one error kind on dev rows; refuse any measure-only test example."""
        leaked = sorted(set(rows) & self.test_ids)
        if leaked:
            raise MeasureOnlySplitError(f"test split examples cannot be inspected: {leaked[:3]}")
        error, short = kind.split("-")
        stance = STANCES[short]
        listed = []
        for identifier, row in sorted(rows.items()):
            golden = self.gold(identifier)
            predicted = predicted_stances(row)
            for name in sorted(set(golden) | set(predicted)):
                gold = stance in golden.get(name, set())
                pred = any(value == stance for value, _, _ in predicted.get(name, []))
                if (error == "FP" and pred and not gold) or (error == "FN" and gold and not pred):
                    listed.append(
                        (identifier, name, sorted(golden.get(name, set())), predicted.get(name, []))
                    )
        return listed


def _runs(values: Sequence[str]) -> list[tuple[str, Path]]:
    runs = []
    for value in values:
        label, _, path = value.partition("=")
        runs.append((label, Path(path)))
    return runs


def main(arguments: Sequence[str] | None = None) -> None:
    """Print a report, stage breakdown or dev-only error listing."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("report", "stages", "errors"))
    parser.add_argument("runs", nargs="+", help="LABEL=comparisons.jsonl")
    parser.add_argument("--split", choices=("all", "dev", "test"), default="dev")
    parser.add_argument("--kind", default="FN-neg", help="FP-neg, FN-neg, FP-pos or FN-pos")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--registry-seed", type=Path, default=DEFAULT_SEED)
    args = parser.parse_args(arguments)
    report = StanceReport(args.annotations, args.registry_seed)
    if args.command == "errors":
        if args.split != "dev":
            raise MeasureOnlySplitError("error listings are available for --split dev only")
        label, path = _runs(args.runs)[0]
        for identifier, name, gold, predicted in report.errors(report.rows(path, "dev"), args.kind)[
            : args.limit
        ]:
            print(f"{args.kind} {identifier} {name}: gold={gold}")
            for stance, source, evidence in predicted[:3]:
                print(f"    [{stance}/{source}] {evidence[:200]}")
        return
    loaded = [(label, report.rows(path, args.split)) for label, path in _runs(args.runs)]
    shared = set.intersection(*(set(rows) for _, rows in loaded))
    loaded = [(label, {key: rows[key] for key in shared}) for label, rows in loaded]
    print(f"{len(shared)} shared examples, split={args.split}")
    if args.command == "stages":
        for label, rows in loaded:
            for short, stance in STANCES.items():
                print(f"{label:12s} {short} {dict(sorted(report.stages(rows, stance).items()))}")
        return
    for short, stance in STANCES.items():
        counts = [report.counts(rows, stance) for _, rows in loaded]
        draws = bootstrap(counts)
        for index, (label, _) in enumerate(loaded):
            precision, recall, score = f1(counts[index].values())
            low, high = interval([draw[index] for draw in draws])
            print(
                f"{label:12s} {short} P/R/F1={precision:.2f}/{recall:.2f}/{score:.3f} "
                f"95% CI [{low:.3f}, {high:.3f}]"
            )
        for index in range(1, len(loaded)):
            difference = f1(counts[index].values())[2] - f1(counts[index - 1].values())[2]
            low, high = interval([draw[index] - draw[index - 1] for draw in draws])
            print(
                f"    {short} {loaded[index][0]} - {loaded[index - 1][0]}: {difference:+.3f} "
                f"95% CI [{low:+.3f}, {high:+.3f}]"
            )


if __name__ == "__main__":
    main()
