ALTER TABLE inference_pass_attempts
    ADD COLUMN IF NOT EXISTS sanitized_payload JSONB,
    ADD COLUMN IF NOT EXISTS finish_reason TEXT,
    ADD COLUMN IF NOT EXISTS completion_tokens INTEGER;

ALTER TABLE analysis_runs ALTER COLUMN pipeline_version SET DEFAULT 'inference_v3_1';

CREATE TABLE IF NOT EXISTS inference_pass_diagnostics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    pass_name TEXT NOT NULL CHECK (pass_name IN ('entities', 'claims', 'classification')),
    raw_primary_output TEXT,
    sanitized_primary_payload JSONB,
    primary_validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_repair_output TEXT,
    sanitized_repair_payload JSONB,
    repair_validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_validation_status TEXT NOT NULL CHECK (
        final_validation_status IN ('valid', 'invalid', 'generation_failure')
    ),
    final_parsed_payload JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, pass_name)
);
