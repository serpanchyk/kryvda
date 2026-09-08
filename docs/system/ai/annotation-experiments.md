# Annotation and Offline Experiments

`golden_v0` is a manually annotated pilot dataset for per-Post-Revision semantic extraction. It
contains entity mentions, registry resolution, attributed stance, atomic claims, modality, and
rhetorical features. It deliberately excludes narratives, waves, campaigns, coordination, attack
scores, and post-level information-attack labels.

The extraction and resolution responsibilities are separate. Extraction finds the exact textual
surface mention. Resolution uses the entity registry and aliases to return a canonical registry
entity when possible. An unresolved mention remains a candidate for review; the model must not
invent a canonical identity.

The `experiments/datasets/` and `experiments/dspy/` directories are offline-only. Their data,
run outputs, and model artifacts are DVC-tracked; code, schemas, guidelines, and DVC metadata are
Git-tracked. No DVC remote is configured until project storage and access control are decided.

DSPy work begins only after the annotation schema is stable. Its evaluation uses component metrics
for entity extraction/resolution, stance, claims, attribution/modality, and rhetorical features,
with a documented weighted aggregate.
