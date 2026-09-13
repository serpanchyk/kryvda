ALTER TABLE claims DROP COLUMN IF EXISTS presentation;

ALTER TABLE inference_pass_attempts
    ADD COLUMN IF NOT EXISTS sanitization_actions JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE inference_pass_diagnostics
    ADD COLUMN IF NOT EXISTS primary_sanitization_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS repair_sanitization_actions JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE analysis_runs ALTER COLUMN pipeline_version SET DEFAULT 'inference_v3_2';
