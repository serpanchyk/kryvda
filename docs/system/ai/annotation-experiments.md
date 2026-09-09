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

The local annotation UI is documented in `experiments/annotation-ui/README.md`. Its standalone
Compose service serves a React editor through an experimental FastAPI backend. It reads existing
Post Revisions with read-only transactions through the existing Compose PostgreSQL network,
freezes their source text on selection, and maintains
drafts and registry candidates in DVC-tracked files. Finalization checks schema and evidence links.
The recovery state is `data/editor.json`; the JSONL files are derived exports. PostgreSQL has no
annotation tables. The editor must be stopped before manually capturing a DVC snapshot.
