CREATE TABLE registry_entities (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,
    coarse_type TEXT NOT NULL CHECK (
        coarse_type IN ('person', 'organization', 'state_institution', 'media')
    ),
    monitored BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE entity_aliases (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES registry_entities(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_id, alias)
);

CREATE TABLE candidate_entities (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    normalized_key TEXT NOT NULL UNIQUE,
    representative_mention TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'linked', 'ignored')),
    linked_entity_id BIGINT REFERENCES registry_entities(id),
    occurrence_count INTEGER NOT NULL DEFAULT 0,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((status = 'linked') = (linked_entity_id IS NOT NULL))
);

CREATE TABLE entity_alias_candidates (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES registry_entities(id) ON DELETE CASCADE,
    surface_form TEXT NOT NULL,
    normalized_form TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'ignored')),
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_id, normalized_form)
);

CREATE TABLE analysis_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    post_revision_id BIGINT NOT NULL REFERENCES post_revisions(id),
    priority TEXT NOT NULL CHECK (priority IN ('live', 'backfill')),
    trigger_kind TEXT NOT NULL DEFAULT 'collection' CHECK (
        trigger_kind IN ('collection', 'entity_created', 'monitoring_enabled', 'alias_added', 'manual')
    ),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'leased', 'completed', 'failed', 'skipped')
    ),
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    leased_until TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error_kind TEXT,
    last_error TEXT,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX analysis_jobs_active_revision_idx
    ON analysis_jobs (post_revision_id) WHERE status IN ('pending', 'leased');
CREATE INDEX analysis_jobs_available_idx ON analysis_jobs (status, priority, available_at);

CREATE TABLE analysis_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id BIGINT NOT NULL UNIQUE REFERENCES analysis_jobs(id),
    post_revision_id BIGINT NOT NULL REFERENCES post_revisions(id),
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    matched_entity_ids BIGINT[] NOT NULL DEFAULT '{}',
    model_name TEXT NOT NULL,
    pipeline_version TEXT NOT NULL DEFAULT 'inference_v3_2',
    final_payload JSONB,
    failure_kind TEXT,
    failure_detail JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE inference_pass_attempts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    pass_name TEXT NOT NULL CHECK (pass_name IN ('entities', 'claims', 'classification')),
    attempt_kind TEXT NOT NULL CHECK (attempt_kind IN ('primary', 'repair')),
    prompt_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    raw_output TEXT,
    parsed_payload JSONB,
    status TEXT NOT NULL CHECK (status IN ('valid', 'invalid', 'failed')),
    failure_kind TEXT,
    validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, pass_name, attempt_kind)
);

CREATE TABLE post_entities (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    local_id TEXT NOT NULL,
    registry_entity_id BIGINT REFERENCES registry_entities(id),
    candidate_entity_id BIGINT REFERENCES candidate_entities(id),
    monitored BOOLEAN NOT NULL,
    mentions JSONB NOT NULL,
    UNIQUE (run_id, local_id),
    CHECK (NOT (registry_entity_id IS NOT NULL AND candidate_entity_id IS NOT NULL))
);

CREATE TABLE claims (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    local_id TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    evidence_text TEXT NOT NULL,
    evidence_start INTEGER NOT NULL,
    evidence_end INTEGER NOT NULL,
    source_kind TEXT NOT NULL CHECK (
        source_kind IN ('channel_editorial', 'named_entity', 'external_unnamed')
    ),
    source_post_entity_id BIGINT REFERENCES post_entities(id),
    epistemic_status TEXT NOT NULL CHECK (
        epistemic_status IN ('ствердження', 'невпевнене', 'питання')
    ),
    UNIQUE (run_id, local_id)
);

CREATE TABLE claim_entities (
    claim_id BIGINT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    post_entity_id BIGINT NOT NULL REFERENCES post_entities(id),
    PRIMARY KEY (claim_id, post_entity_id)
);

CREATE TABLE claim_target_classifications (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    claim_id BIGINT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    post_entity_id BIGINT NOT NULL REFERENCES post_entities(id),
    stance TEXT NOT NULL CHECK (stance IN ('позитивне', 'негативне', 'відсутнє')),
    rhetoric JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (claim_id, post_entity_id)
);

CREATE INDEX candidate_entities_review_idx
    ON candidate_entities (status, occurrence_count DESC, last_seen_at DESC);
CREATE INDEX analysis_runs_revision_idx
    ON analysis_runs (post_revision_id, created_at DESC);
