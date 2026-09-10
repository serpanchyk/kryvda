ALTER TABLE analysis_jobs
    ADD COLUMN IF NOT EXISTS last_error_kind TEXT,
    ADD COLUMN IF NOT EXISTS last_error TEXT,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS post_analysis_extractions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    post_revision_id BIGINT NOT NULL UNIQUE REFERENCES post_revisions(id),
    payload JSONB NOT NULL,
    prompt_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
