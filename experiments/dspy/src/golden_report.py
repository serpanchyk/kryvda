"""Canonical semantic benchmark metrics, partitioned by legacy and held-out provenance."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from golden_schema import CanonicalGolden, GoldenClassification

RHETORIC_LABELS = (
    "корупція_або_особиста_вигода",
    "злочинна_або_незаконна_поведінка",
    "делегітимізація",
    "лицемірство_або_подвійні_стандарти",
    "висміювання_або_особиста_образа",
    "зовнішній_контроль_або_нелояльність",
)


@dataclass(frozen=True)
class EvaluationItem:
    """One aligned evaluation result; adapters run before this boundary."""

    golden: CanonicalGolden
    prediction: CanonicalGolden | None
    degraded: bool = False


def benchmark_report(items: Iterable[EvaluationItem]) -> dict[str, dict[str, Any]]:
    """Return explicit old55/new45/all100 semantic and reliability metrics.

    Predictions must already use the canonical IDs established by the evaluator's claim/entity
    alignment step. This module intentionally has no schema-version branches.
    """
    all_items = list(items)
    old = [item for item in all_items if item.golden.original_schema_version != "golden_v1"]
    new = [item for item in all_items if item.golden.original_schema_version == "golden_v1"]
    return {
        "OLD 55 - legacy adapter": _section(old, legacy=True),
        "NEW 45 - held-out golden_v1": _section(new, legacy=False),
        "ALL 100": _section(all_items, provenance="mixed"),
    }


def _section(
    items: list[EvaluationItem], legacy: bool | None = None, provenance: str | None = None
) -> dict[str, Any]:
    expected_claims = sum(len(item.golden.claims) for item in items)
    retained_claims = sum(
        len(item.prediction.claims) if item.prediction is not None else 0 for item in items
    )
    matched_claims = sum(_matched_claims(item) for item in items)
    classifications = [
        (golden, predicted)
        for item in items
        for golden, predicted in _aligned_classifications(item)
    ]
    excluded = Counter(
        warning["kind"]
        for item in items
        for warning in item.golden.mapping_warnings
        if warning["kind"]
        in {"unmapped_legacy_rhetoric", "ambiguous_rhetoric_claim", "unresolved_legacy_stance"}
    )
    stance_pairs = [(golden.stance, predicted.stance) for golden, predicted in classifications]
    rhetoric_pairs = [
        (golden.rhetoric, predicted.rhetoric) for golden, predicted in classifications
    ]
    completed = sum(item.prediction is not None for item in items)
    attacks = [(bool(gold), bool(pred)) for gold, pred in rhetoric_pairs]
    return {
        "provenance": provenance or ("legacy_adapter" if legacy else "native_golden_v1"),
        "examples": len(items),
        "retained_claim_count": retained_claims,
        "claim_coverage": _ratio(matched_claims, expected_claims),
        "attribution_confusion_matrix": _claim_confusion(items, "attribution"),
        "epistemic_confusion_matrix": _claim_confusion(items, "epistemic_status"),
        "stance": _multiclass_metrics(stance_pairs),
        "rhetoric_per_label": {
            label: _label_metrics(rhetoric_pairs, label) for label in RHETORIC_LABELS
        },
        "rhetoric_micro_f1": _micro_f1(rhetoric_pairs),
        "rhetoric_macro_f1": _macro_f1(rhetoric_pairs),
        "attack_detection": _binary_metrics(attacks),
        "reliability": _ratio(completed, len(items)),
        "degradation_rate": _ratio(sum(item.degraded for item in items), len(items)),
        "excluded_legacy_or_ambiguous_annotations": dict(sorted(excluded.items())),
    }


def _matched_claims(item: EvaluationItem) -> int:
    if item.prediction is None:
        return 0
    prediction_ids = {claim.id for claim in item.prediction.claims}
    return sum(claim.id in prediction_ids for claim in item.golden.claims)


def _claim_confusion(items: list[EvaluationItem], field: str) -> dict[str, dict[str, int]]:
    counts: Counter[tuple[str, str]] = Counter()
    for item in items:
        if item.prediction is None:
            continue
        predicted = {claim.id: claim for claim in item.prediction.claims}
        for golden in item.golden.claims:
            candidate = predicted.get(golden.id)
            if candidate is None:
                continue
            expected = (
                golden.attribution["source_kind"]
                if field == "attribution"
                else golden.epistemic_status
            )
            actual = (
                candidate.attribution["source_kind"]
                if field == "attribution"
                else candidate.epistemic_status
            )
            if expected is not None and actual is not None:
                counts[(expected, actual)] += 1
    return _confusion(counts)


def _aligned_classifications(
    item: EvaluationItem,
) -> list[tuple[GoldenClassification, GoldenClassification]]:
    if item.prediction is None:
        return []
    predicted = {
        (value.claim_id, value.entity_id): value for value in item.prediction.classifications
    }
    return [
        (golden, predicted[(golden.claim_id, golden.entity_id)])
        for golden in item.golden.classifications
        if golden.stance is not None and (golden.claim_id, golden.entity_id) in predicted
    ]


def _multiclass_metrics(pairs: list[tuple[str | None, str | None]]) -> dict[str, dict[str, float]]:
    labels = ("позитивне", "негативне", "відсутнє")
    return {
        label: _prf(
            sum(expected == label and actual == label for expected, actual in pairs),
            sum(expected != label and actual == label for expected, actual in pairs),
            sum(expected == label and actual != label for expected, actual in pairs),
        )
        for label in labels
    }


def _label_metrics(pairs: list[tuple[list[str], list[str]]], label: str) -> dict[str, float]:
    return _prf(
        sum(label in expected and label in actual for expected, actual in pairs),
        sum(label not in expected and label in actual for expected, actual in pairs),
        sum(label in expected and label not in actual for expected, actual in pairs),
    )


def _micro_f1(pairs: list[tuple[list[str], list[str]]]) -> float:
    expected = {(index, label) for index, (labels, _) in enumerate(pairs) for label in labels}
    actual = {(index, label) for index, (_, labels) in enumerate(pairs) for label in labels}
    return _prf(len(expected & actual), len(actual - expected), len(expected - actual))["f1"]


def _macro_f1(pairs: list[tuple[list[str], list[str]]]) -> float:
    return _ratio(
        sum(_label_metrics(pairs, label)["f1"] for label in RHETORIC_LABELS),
        len(RHETORIC_LABELS),
    )


def _binary_metrics(pairs: list[tuple[bool, bool]]) -> dict[str, float]:
    return _prf(
        sum(expected and actual for expected, actual in pairs),
        sum(not expected and actual for expected, actual in pairs),
        sum(expected and not actual for expected, actual in pairs),
    )


def _prf(true_positive: int, false_positive: int, false_negative: int) -> dict[str, float]:
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    return {
        "precision": precision,
        "recall": recall,
        "f1": _ratio(2 * precision * recall, precision + recall),
    }


def _confusion(counts: Counter[tuple[str, str]]) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for (expected, actual), count in sorted(counts.items()):
        output.setdefault(expected, {})[actual] = count
    return output


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
