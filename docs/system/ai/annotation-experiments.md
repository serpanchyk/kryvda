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

`mamay_vs_golden_v3_5_1` is the DVC-tracked 100-post, production-aligned three-pass Mamay
comparison artifact. It contains raw inference diagnostics and a standalone contract-health
summary; it intentionally does not calculate a numeric delta against the 55-post v3.5 artifact.

`mamay_vs_golden_v3_5_2` reruns the same 100 examples with the v3.5.2 alias and stance semantics.
Its canonical-only semantic report partitions the tuned data as `old55`, `diagnostic45`, and
`all100`; the 45 diagnostic examples are not described as held-out after this tuning.

`jev_vs_golden_v1` is a DVC-tracked, classification-only comparison of TypeSafe's Jev typed
decisions (through OpenRouter) on the same 100 examples. Reviewed claims and attribution are
inputs; it scores stance, rhetoric, epistemic status, and presentation in both the production and
the extended `golden_v0` taxonomy, and compares Jev with Mamay v3.5.2 on Mamay's aligned pairs. It
is an external-provider experiment, not a production dependency. Prompt versions `v2` to `v4` were
iterated on `old55` only and stored as `jev_vs_golden_v2` (`old55`), `jev_vs_golden_v3`, and
`jev_vs_golden_v4`; `diagnostic45` was scored once per final version.

`jev_hybrid_v3_6` is the end-to-end check: Jev prompt `v4` classifies the claims that Mamay v3.6
extracted in `mamay_vs_golden_v3_6`, so both variants share the same imperfect extraction and the
same canonical evaluation. On `diagnostic45` it ties Mamay on stance, improves rhetoric labels and
claim-target attack detection, and lowers post-level attack recall and epistemic accuracy.

DSPy work begins only after the annotation schema is stable. Its evaluation uses component metrics
for entity extraction/resolution, stance, claims, attribution/modality, and rhetorical features,
with a documented weighted aggregate.

`golden_v0` holds 500 examples; its `extension400` partition was annotated by Claude subagents. Posts are selected read-only from PostgreSQL with the production registry matcher,
square-root channel quotas, a 65% share of anti-corruption core actors, and an 8% per-entity cap.
Annotators write exact quotes rather than offsets; `golden_v0_anchor.py` resolves them to spans
and applies the editor's import and full-record checks, and the import itself goes through the
editor's `complete-import` endpoint. A blind re-annotation of ten `diagnostic45` posts measures
agreement with the original annotations. The original 100 were drafted by ChatGPT with web access
and partly reviewed by the user; the provenance file records both origins.

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
