"""Canonical semantic benchmark metrics for the tuned old55/diagnostic45 benchmark."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from golden_schema import CanonicalGolden, GoldenClaim, GoldenClassification, GoldenEntity

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


def canonical_prediction(
    final_output: Mapping[str, Any] | None, golden: CanonicalGolden
) -> CanonicalGolden | None:
    """Adapt one inference result to canonical IDs before evaluation.

    This is an evaluation-boundary adapter, not inference logic.  It uses canonical entity names
    and grounded evidence overlap to align locally generated IDs with the reviewed annotation.
    """
    if final_output is None:
        return None
    golden_entities = {
        entity.canonical_name: entity for entity in golden.entities if entity.canonical_name
    }
    entity_ids: dict[str, str] = {}
    entities: list[GoldenEntity] = []
    for entity in _mappings(final_output.get("entities")):
        canonical_name = entity.get("canonical_name")
        if not isinstance(canonical_name, str) or canonical_name not in golden_entities:
            continue
        source_id = entity.get("id")
        if not isinstance(source_id, str):
            continue
        target = golden_entities[canonical_name]
        entity_ids[source_id] = target.id
        if target not in entities:
            entities.append(target)
    claims: list[GoldenClaim] = []
    claim_ids: dict[str, str] = {}
    used_golden_claims: set[str] = set()
    for claim in _mappings(final_output.get("claims")):
        source_id = claim.get("id")
        evidence = claim.get("evidence_text")
        if not isinstance(source_id, str) or not isinstance(evidence, str):
            continue
        candidates = [
            value
            for value in golden.claims
            if value.id not in used_golden_claims and _evidence_overlap(value, evidence) > 0
        ]
        if not candidates:
            continue
        target = max(candidates, key=lambda value: _evidence_overlap(value, evidence))
        used_golden_claims.add(target.id)
        claim_ids[source_id] = target.id
        attribution = claim.get("attribution")
        if not isinstance(attribution, Mapping):
            continue
        claim_entities = [
            entity_ids[value]
            for value in claim.get("entity_ids", [])
            if isinstance(value, str) and value in entity_ids
        ]
        claims.append(
            GoldenClaim(
                id=target.id,
                normalized_text=str(claim.get("normalized_text", "")),
                entity_ids=claim_entities,
                evidence_text=evidence,
                attribution={
                    "source_kind": str(attribution.get("source_kind", "")),
                    "source_entity_id": attribution.get("source_entity_id"),
                },
                epistemic_status=str(claim.get("epistemic_status", "")),
            )
        )
    classifications: list[GoldenClassification] = []
    for row in _mappings(final_output.get("classifications")):
        claim_id, entity_id, stance, rhetoric = (
            row.get("claim_id"),
            row.get("entity_id"),
            row.get("stance"),
            row.get("rhetoric"),
        )
        if (
            not isinstance(claim_id, str)
            or not isinstance(entity_id, str)
            or not isinstance(stance, str)
            or not isinstance(rhetoric, list)
            or claim_id not in claim_ids
            or entity_id not in entity_ids
        ):
            continue
        classifications.append(
            GoldenClassification(
                claim_ids[claim_id],
                entity_ids[entity_id],
                stance,
                [str(value) for value in rhetoric],
            )
        )
    return CanonicalGolden(
        example_id=golden.example_id,
        source_text=golden.source_text,
        entities=entities,
        claims=claims,
        classifications=classifications,
        original_schema_version="inference_output_v3_5_2",
    )


def benchmark_report(
    items: Iterable[EvaluationItem], old55_example_ids: set[str]
) -> dict[str, dict[str, Any]]:
    """Return explicit old55/diagnostic45/all100 semantic and reliability metrics.

    Predictions must already use the canonical IDs established by the evaluator's claim/entity
    alignment step. This module intentionally has no schema-version branches.
    """
    all_items = list(items)
    old = [item for item in all_items if item.golden.example_id in old55_example_ids]
    diagnostic = [item for item in all_items if item.golden.example_id not in old55_example_ids]
    return {
        "old55": _section(old, provenance="legacy_adapter"),
        "diagnostic45": _section(diagnostic, provenance="legacy_adapter_tuned"),
        "all100": _section(all_items, provenance="mixed"),
    }


def _section(items: list[EvaluationItem], provenance: str) -> dict[str, Any]:
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
        in {
            "unmapped_legacy_rhetoric",
            "ambiguous_rhetoric_claim",
            "unresolved_legacy_stance",
            "unresolved_legacy_epistemic",
        }
    )
    stance_pairs = [(golden.stance, predicted.stance) for golden, predicted in classifications]
    rhetoric_pairs = [
        (golden.rhetoric, predicted.rhetoric) for golden, predicted in classifications
    ]
    completed = sum(item.prediction is not None for item in items)
    attacks = [(bool(gold), bool(pred)) for gold, pred in rhetoric_pairs]
    entity_attacks = _entity_attack_pairs(items)
    post_attacks = _post_attack_pairs(items)
    return {
        "provenance": provenance,
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
        "entity_level_attack_detection": _binary_metrics(entity_attacks),
        "post_level_attack_detection": {
            **_binary_metrics([(gold, predicted) for _, gold, predicted in post_attacks]),
            "false_positive_ids": [
                identifier for identifier, gold, predicted in post_attacks if predicted and not gold
            ],
            "false_negative_ids": [
                identifier for identifier, gold, predicted in post_attacks if gold and not predicted
            ],
        },
        "claim_target_attack_detection": _binary_metrics(attacks),
        "reliability": _ratio(completed, len(items)),
        "degradation_rate": _ratio(sum(item.degraded for item in items), len(items)),
        "unresolved_or_excluded_legacy_annotations": dict(sorted(excluded.items())),
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


def _entity_attack_pairs(items: list[EvaluationItem]) -> list[tuple[bool, bool]]:
    """Aggregate rhetoric attack presence by canonical entity within each post."""
    pairs: list[tuple[bool, bool]] = []
    for item in items:
        if item.prediction is None:
            continue
        golden = _classification_attacks_by_entity(item.golden.classifications)
        predicted = _classification_attacks_by_entity(item.prediction.classifications)
        for entity_id in sorted(set(golden) | set(predicted)):
            pairs.append((golden.get(entity_id, False), predicted.get(entity_id, False)))
    return pairs


def _post_attack_pairs(items: list[EvaluationItem]) -> list[tuple[str, bool, bool]]:
    """Aggregate rhetoric attack presence by post and retain exact diagnostic IDs."""
    return [
        (
            item.golden.example_id,
            any(bool(value.rhetoric) for value in item.golden.classifications),
            bool(item.prediction)
            and any(bool(value.rhetoric) for value in item.prediction.classifications),
        )
        for item in items
    ]


def _classification_attacks_by_entity(
    classifications: list[GoldenClassification],
) -> dict[str, bool]:
    attacks: dict[str, bool] = {}
    for classification in classifications:
        attacks[classification.entity_id] = attacks.get(classification.entity_id, False) or bool(
            classification.rhetoric
        )
    return attacks


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


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        return []
    return list(value)


def _evidence_overlap(claim: GoldenClaim, evidence: str) -> int:
    """Return a conservative overlap score between golden and generated evidence."""
    if evidence in claim.evidence_text or claim.evidence_text in evidence:
        return min(len(evidence), len(claim.evidence_text))
    return 0
