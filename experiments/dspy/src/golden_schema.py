"""Versioned golden-dataset loading and canonicalisation for semantic evaluation.

The canonical form is deliberately the only input an evaluator needs.  Legacy conversion is
loss-aware: an uncertain conversion is recorded and excluded at item level, never guessed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

CANONICAL_SCHEMA_VERSION = "canonical_golden_v1"
GOLDEN_V0_SCHEMA_VERSION = "annotation_schema_v1"
GOLDEN_V1_SCHEMA_VERSION = "golden_v1"

EPISTEMIC_MAP = {
    "asserted": "ствердження",
    "alleged": "невпевнене",
    "hypothetical": "невпевнене",
    "questioned": "питання",
}
STANCE_MAP = {"negative": "негативне", "positive": "позитивне", "neutral": "відсутнє"}
RHETORIC_MAP = {
    "corruption_accusation": "корупція_або_особиста_вигода",
    "criminality_accusation": "злочинна_або_незаконна_поведінка",
    "delegitimization": "делегітимізація",
    "hypocrisy_claim": "лицемірство_або_подвійні_стандарти",
    "ridicule": "висміювання_або_особиста_образа",
    "derogatory_labeling": "висміювання_або_особиста_образа",
    "foreign_control_accusation": "зовнішній_контроль_або_нелояльність",
}
UNMAPPED_RHETORIC = {"grant_discrediting", "call_for_punishment"}


@dataclass(frozen=True)
class GoldenEntity:
    id: str
    registry_entity_id: int | str | None
    canonical_name: str | None
    monitored: bool


@dataclass(frozen=True)
class GoldenClaim:
    id: str
    normalized_text: str
    entity_ids: list[str]
    evidence_text: str
    attribution: dict[str, str | None]
    epistemic_status: str | None
    evidence_start: int | None = None
    evidence_end: int | None = None


@dataclass(frozen=True)
class GoldenClassification:
    claim_id: str
    entity_id: str
    stance: str | None
    rhetoric: list[str]


@dataclass
class CanonicalGolden:
    example_id: str
    source_text: str
    entities: list[GoldenEntity]
    claims: list[GoldenClaim]
    classifications: list[GoldenClassification]
    original_schema_version: str
    mapping_actions: list[dict[str, Any]] = field(default_factory=list)
    mapping_warnings: list[dict[str, Any]] = field(default_factory=list)
    unmapped_legacy_labels: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_mappings: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return an inspectable generated representation."""
        return {"schema_version": CANONICAL_SCHEMA_VERSION, **asdict(self)}


class GoldenV1Adapter:
    """Validate and load native golden_v1 records without semantic remapping."""

    def __init__(self, schema_path: Path) -> None:
        self._validator = Draft202012Validator(_load_schema(schema_path))

    def convert(self, record: Mapping[str, Any]) -> CanonicalGolden:
        errors = sorted(self._validator.iter_errors(record), key=lambda error: list(error.path))
        if errors:
            detail = "; ".join(error.message for error in errors)
            raise ValueError(f"invalid golden_v1 record: {detail}")
        source = _mapping(record["source"])
        source_text = _string(source["text"], "source.text")
        entities = [
            GoldenEntity(
                id=_string(entity["id"], "entity.id"),
                registry_entity_id=entity.get("registry_entity_id"),
                canonical_name=entity.get("canonical_name"),
                monitored=_bool(entity["monitored"], "entity.monitored"),
            )
            for entity in _mappings(record["entities"])
        ]
        claims = [self._claim(claim, source_text) for claim in _mappings(record["claims"])]
        classifications = [
            GoldenClassification(
                claim_id=_string(item["claim_id"], "classification.claim_id"),
                entity_id=_string(item["entity_id"], "classification.entity_id"),
                stance=_string(item["stance"], "classification.stance"),
                rhetoric=[_string(label, "classification.rhetoric") for label in item["rhetoric"]],
            )
            for item in _mappings(record["classifications"])
        ]
        _validate_native_relationships(entities, claims, classifications)
        return CanonicalGolden(
            example_id=_string(record["example_id"], "example_id"),
            source_text=source_text,
            entities=entities,
            claims=claims,
            classifications=classifications,
            original_schema_version=GOLDEN_V1_SCHEMA_VERSION,
        )

    @staticmethod
    def _claim(claim: Mapping[str, Any], source_text: str) -> GoldenClaim:
        evidence = _string(claim["evidence_text"], "claim.evidence_text")
        start = claim.get("evidence_start")
        end = claim.get("evidence_end")
        if evidence not in source_text:
            raise ValueError("golden_v1 claim evidence_text is not grounded in source.text")
        if start is not None and source_text[start:end] != evidence:
            raise ValueError("golden_v1 evidence offsets do not select evidence_text")
        attribution = _mapping(claim["attribution"])
        return GoldenClaim(
            id=_string(claim["id"], "claim.id"),
            normalized_text=_string(claim["normalized_text"], "claim.normalized_text"),
            entity_ids=[_string(value, "claim.entity_ids") for value in claim["entity_ids"]],
            evidence_text=evidence,
            attribution={
                "source_kind": _string(attribution["source_kind"], "attribution.source_kind"),
                "source_entity_id": attribution.get("source_entity_id"),
            },
            epistemic_status=_string(claim["epistemic_status"], "claim.epistemic_status"),
            evidence_start=start if isinstance(start, int) else None,
            evidence_end=end if isinstance(end, int) else None,
        )


class GoldenV0Adapter:
    """Deterministically adapt immutable annotation_schema_v1 records."""

    def convert(self, record: Mapping[str, Any]) -> CanonicalGolden:
        source = _mapping(record["source"])
        source_text = _string(source["text"], "source.text")
        annotations = _mapping(record["annotations"])
        old_entities = _mappings(annotations["entities"])
        entities = [
            GoldenEntity(
                id=_string(entity["id"], "entity.id"),
                registry_entity_id=entity.get("registry_entity_id"),
                canonical_name=entity.get("canonical_name"),
                # v0 predates the production registry. Locally resolved candidates were the
                # annotator's in-scope targets; dropping them would erase the old55 benchmark.
                monitored=entity.get("registry_status") in {"candidate", "monitored"},
            )
            for entity in old_entities
        ]
        actions: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        candidate_entities = [
            entity["id"] for entity in old_entities if entity.get("registry_status") == "candidate"
        ]
        if candidate_entities:
            actions.append(
                {
                    "kind": "legacy_candidates_treated_as_evaluable_targets",
                    "entity_ids": candidate_entities,
                }
            )
        claims = [
            self._claim(claim, source_text, actions, warnings)
            for claim in _mappings(annotations["claims"])
        ]
        classifications = self._classifications(
            claims,
            entities,
            _mappings(annotations["stances"]),
            _mappings(annotations["rhetorical_features"]),
            actions,
            warnings,
        )
        result = CanonicalGolden(
            example_id=_string(record["example_id"], "example_id"),
            source_text=source_text,
            entities=entities,
            claims=claims,
            classifications=classifications,
            original_schema_version=GOLDEN_V0_SCHEMA_VERSION,
            mapping_actions=actions,
            mapping_warnings=warnings,
        )
        result.unmapped_legacy_labels = [
            warning for warning in warnings if warning["kind"] == "unmapped_legacy_rhetoric"
        ]
        result.ambiguous_mappings = [
            warning for warning in warnings if warning["kind"] == "ambiguous_rhetoric_claim"
        ]
        return result

    def _claim(
        self,
        claim: Mapping[str, Any],
        text: str,
        actions: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> GoldenClaim:
        spans = _mappings(claim["evidence_spans"])
        start, end = _span(spans[0])
        old_epistemic = _string(claim["epistemic_status"], "claim.epistemic_status")
        epistemic = EPISTEMIC_MAP.get(old_epistemic)
        if epistemic is None:
            warnings.append(
                {
                    "kind": "unresolved_legacy_epistemic",
                    "claim_id": claim["id"],
                    "legacy_value": old_epistemic,
                    "resolution": "unresolved_legacy",
                }
            )
        else:
            actions.append(
                {
                    "kind": "epistemic_mapped",
                    "claim_id": claim["id"],
                    "from": old_epistemic,
                    "to": epistemic,
                }
            )
        attribution = _mapping(claim["attribution"])
        return GoldenClaim(
            id=_string(claim["id"], "claim.id"),
            normalized_text=_string(claim["normalized_text"], "claim.normalized_text"),
            entity_ids=[_string(value, "claim.entity_ids") for value in claim["entity_ids"]],
            evidence_text=text[start:end],
            evidence_start=start,
            evidence_end=end,
            attribution={
                "source_kind": _string(attribution["source_kind"], "attribution.source_kind"),
                "source_entity_id": attribution.get("source_entity_id"),
            },
            epistemic_status=epistemic,
        )

    def _classifications(
        self,
        claims: list[GoldenClaim],
        entities: list[GoldenEntity],
        stances: list[Mapping[str, Any]],
        features: list[Mapping[str, Any]],
        actions: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> list[GoldenClassification]:
        monitored = {entity.id for entity in entities if entity.monitored}
        classifications: dict[tuple[str, str], GoldenClassification] = {}
        for claim in claims:
            for entity_id in claim.entity_ids:
                if entity_id not in monitored:
                    continue
                selected = self._select_stance(claim, entity_id, stances, warnings)
                stance = None if selected is None else STANCE_MAP.get(selected.get("value"))
                if selected is not None and stance is None:
                    warnings.append(
                        {
                            "kind": "unresolved_legacy_stance",
                            "claim_id": claim.id,
                            "entity_id": entity_id,
                            "legacy_value": selected.get("value"),
                            "resolution": "unresolved_legacy",
                        }
                    )
                elif stance is not None:
                    actions.append(
                        {
                            "kind": "stance_mapped",
                            "claim_id": claim.id,
                            "entity_id": entity_id,
                            "to": stance,
                        }
                    )
                classifications[(claim.id, entity_id)] = GoldenClassification(
                    claim.id, entity_id, stance, []
                )
        for feature in features:
            self._attach_feature(feature, claims, classifications, actions, warnings)
        return list(classifications.values())

    @staticmethod
    def _select_stance(
        claim: GoldenClaim,
        entity_id: str,
        stances: list[Mapping[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> Mapping[str, Any] | None:
        candidates = [stance for stance in stances if stance.get("entity_id") == entity_id]
        overlapping = [
            stance
            for stance in candidates
            if _spans_overlap(claim, _mappings(stance.get("evidence_spans", [])))
        ]
        candidates = overlapping or candidates
        if not candidates:
            warnings.append(
                {
                    "kind": "unresolved_legacy_stance",
                    "claim_id": claim.id,
                    "entity_id": entity_id,
                    "legacy_value": None,
                    "resolution": "unresolved_legacy",
                }
            )
            return None
        compatible = [
            stance for stance in candidates if stance.get("perspective") == claim.attribution
        ]
        candidates = compatible or candidates
        if len(candidates) != 1:
            warnings.append(
                {
                    "kind": "ambiguous_legacy_stance",
                    "claim_id": claim.id,
                    "entity_id": entity_id,
                    "candidate_count": len(candidates),
                }
            )
            return None
        return candidates[0]

    @staticmethod
    def _attach_feature(
        feature: Mapping[str, Any],
        claims: list[GoldenClaim],
        classifications: dict[tuple[str, str], GoldenClassification],
        actions: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> None:
        target_entity = feature.get("target_entity_id")
        if not isinstance(target_entity, str):
            warnings.append(
                {"kind": "unresolved_rhetoric_target", "feature": feature.get("feature_type")}
            )
            return
        target_claim = feature.get("target_claim_id")
        candidates = [claim for claim in claims if target_entity in claim.entity_ids]
        if isinstance(target_claim, str):
            candidates = [claim for claim in candidates if claim.id == target_claim]
        else:
            span = feature.get("evidence_span")
            if not isinstance(span, Mapping):
                warnings.append(
                    {"kind": "unresolved_rhetoric_target", "feature": feature.get("feature_type")}
                )
                return
            feature_span = [span]
            candidates = [claim for claim in candidates if _spans_overlap(claim, feature_span)]
        if len(candidates) != 1:
            warnings.append(
                {
                    "kind": "ambiguous_rhetoric_claim",
                    "feature": feature.get("feature_type"),
                    "target_entity_id": target_entity,
                    "candidate_claim_ids": [claim.id for claim in candidates],
                }
            )
            return
        key = (candidates[0].id, target_entity)
        classification = classifications.get(key)
        if classification is None:
            return
        legacy = feature.get("feature_type")
        mapped = RHETORIC_MAP.get(legacy)
        if mapped is None:
            warnings.append(
                {
                    "kind": "unmapped_legacy_rhetoric",
                    "claim_id": key[0],
                    "entity_id": key[1],
                    "legacy_feature": legacy,
                    "mapped_feature": None,
                }
            )
            return
        rhetoric = [*classification.rhetoric]
        if mapped not in rhetoric:
            rhetoric.append(mapped)
        classifications[key] = GoldenClassification(key[0], key[1], classification.stance, rhetoric)
        actions.append(
            {
                "kind": "rhetoric_mapped",
                "claim_id": key[0],
                "entity_id": key[1],
                "from": legacy,
                "to": mapped,
            }
        )


def load_golden(
    record: Mapping[str, Any], golden_v1_schema_path: Path | None = None
) -> CanonicalGolden:
    """Detect a golden schema version and return its canonical semantic representation."""
    version = record.get("schema_version")
    if version == GOLDEN_V0_SCHEMA_VERSION:
        return GoldenV0Adapter().convert(record)
    if version == GOLDEN_V1_SCHEMA_VERSION:
        schema = golden_v1_schema_path or Path(
            "experiments/datasets/golden_v1/annotation_schema_v1.json"
        )
        return GoldenV1Adapter(schema).convert(record)
    raise ValueError(f"unsupported golden schema version: {version!r}")


def load_golden_jsonl(
    path: Path, golden_v1_schema_path: Path | None = None
) -> list[CanonicalGolden]:
    """Load a mixed JSONL file while rejecting duplicate example IDs."""
    results: list[CanonicalGolden] = []
    identifiers: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        result = load_golden(json.loads(line), golden_v1_schema_path)
        if result.example_id in identifiers:
            raise ValueError(f"duplicate example_id on line {line_number}: {result.example_id}")
        identifiers.add(result.example_id)
        results.append(result)
    return results


def mapping_summary(records: list[CanonicalGolden]) -> dict[str, int]:
    """Summarise exclusions requiring a focused manual inspection."""
    warnings = [warning for record in records for warning in record.mapping_warnings]
    return {
        "examples": len(records),
        "mapped_claims": sum(len(record.claims) for record in records),
        "generated_classifications": sum(len(record.classifications) for record in records),
        "unmapped_rhetoric_labels": sum(
            warning["kind"] == "unmapped_legacy_rhetoric" for warning in warnings
        ),
        "ambiguous_rhetoric_to_claim": sum(
            warning["kind"] == "ambiguous_rhetoric_claim" for warning in warnings
        ),
        "unresolved_stances": sum(
            warning["kind"] == "unresolved_legacy_stance" for warning in warnings
        ),
        "unresolved_epistemics": sum(
            warning["kind"] == "unresolved_legacy_epistemic" for warning in warnings
        ),
    }


def _load_schema(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("schema must be an object")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ValueError("expected array of objects")
    return list(value)


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _span(span: Mapping[str, Any]) -> tuple[int, int]:
    start, end = span.get("start"), span.get("end")
    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError("span must contain integer start and end")
    return start, end


def _spans_overlap(claim: GoldenClaim, spans: list[Mapping[str, Any]]) -> bool:
    if claim.evidence_start is None or claim.evidence_end is None:
        return False
    return any(
        claim.evidence_start < end and start < claim.evidence_end
        for start, end in map(_span, spans)
    )


def _validate_native_relationships(
    entities: list[GoldenEntity],
    claims: list[GoldenClaim],
    classifications: list[GoldenClassification],
) -> None:
    """Validate cross-object v1 invariants not expressed by the JSON Schema."""
    entity_ids = {entity.id for entity in entities}
    claims_by_id = {claim.id: claim for claim in claims}
    if len(entity_ids) != len(entities) or len(claims_by_id) != len(claims):
        raise ValueError("golden_v1 entity and claim IDs must be unique")
    monitored = {entity.id for entity in entities if entity.monitored}
    pairs: set[tuple[str, str]] = set()
    for claim in claims:
        if not set(claim.entity_ids) <= entity_ids:
            raise ValueError("golden_v1 claim references an unknown entity")
    for item in classifications:
        pair = (item.claim_id, item.entity_id)
        if pair in pairs:
            raise ValueError("golden_v1 classifications must be unique per claim-target pair")
        pairs.add(pair)
        claim = claims_by_id.get(item.claim_id)
        if claim is None or item.entity_id not in claim.entity_ids:
            raise ValueError("golden_v1 classification must reference a claim participant")
        if item.entity_id not in monitored:
            raise ValueError("golden_v1 classifications are only allowed for monitored targets")
        if item.stance != "негативне" and item.rhetoric:
            raise ValueError("golden_v1 non-negative classifications must have empty rhetoric")
