# Annotation and Offline Experiments

`golden_v0` is a manually annotated pilot dataset for per-Post-Revision semantic extraction. It
contains entity mentions, registry resolution, attributed stance, atomic claims, modality, and
rhetorical features. It deliberately excludes narratives, waves, campaigns, coordination, attack
scores, and post-level information-attack labels.

The extraction and resolution responsibilities are separate. Extraction finds the exact textual
surface mention. Resolution uses the entity registry and aliases to return a canonical registry
entity when possible. An unresolved mention remains a candidate for review; the model must not
invent a canonical identity.

The shared `extraction_schema_v1` contract is the runtime candidate-extraction shape for the
lesser model. It excludes canonical names and all registry decisions; see
`post-analysis-extraction.md`. It is not a replacement for `golden_v0` review data.

The `experiments/datasets/` and `experiments/dspy/` directories are offline-only. Their data,
run outputs, and model artifacts are DVC-tracked; code, schemas, guidelines, and DVC metadata are
Git-tracked. No DVC remote is configured until project storage and access control are decided.

`mamay_vs_golden_v1` evaluates an experiment-only Mamay v2 contract against a deterministic
projection of `golden_v0`. It is not a migration of `extraction_schema_v1`: production candidate
extraction continues to use its existing schema, prompt, validation, and worker path.

DSPy work begins only after the annotation schema is stable. Its evaluation uses component metrics
for entity extraction/resolution, stance, claims, attribution/modality, and rhetorical features,
with a documented weighted aggregate.

The local annotation UI is documented in `experiments/annotation-ui/README.md`. Its standalone
Compose service serves a React editor through an experimental FastAPI backend. It reads existing
Post Revisions with read-only transactions through the existing Compose PostgreSQL network,
freezes their source text on selection, and maintains
drafts and registry candidates in DVC-tracked files. Finalization checks schema and evidence links.
The UI can also copy a frozen-post package and `annotation_import_schema_v1` for external ChatGPT
annotation. The response contains only mutable selection and annotation fields. Import produces
an editable preview without a write; confirmation reconstructs the full record, validates it,
and only then creates candidate registry entries for previously unseen normalized canonical
name/entity-type pairs.
The recovery state is `data/editor.json`; the JSONL files are derived exports. PostgreSQL has no
annotation tables. The editor must be stopped before manually capturing a DVC snapshot.
