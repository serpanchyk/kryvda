ALTER TABLE analysis_runs DROP CONSTRAINT IF EXISTS analysis_runs_status_check;
ALTER TABLE analysis_runs ADD CONSTRAINT analysis_runs_status_check CHECK (status IN (
    'running', 'completed', 'completed_with_partial_classification',
    'completed_with_entity_fallback', 'failed', 'filtered_out'
));

ALTER TABLE inference_pass_attempts DROP CONSTRAINT IF EXISTS inference_pass_attempts_attempt_kind_check;
ALTER TABLE inference_pass_attempts ADD CONSTRAINT inference_pass_attempts_attempt_kind_check CHECK (
    attempt_kind IN ('primary', 'repair', 'retry')
);

ALTER TABLE inference_pass_diagnostics DROP CONSTRAINT IF EXISTS inference_pass_diagnostics_final_validation_status_check;
ALTER TABLE inference_pass_diagnostics ADD CONSTRAINT inference_pass_diagnostics_final_validation_status_check CHECK (
    final_validation_status IN ('valid', 'invalid', 'generation_failure', 'degraded', 'partial')
);
ALTER TABLE inference_pass_diagnostics
    ADD COLUMN IF NOT EXISTS fallback TEXT,
    ADD COLUMN IF NOT EXISTS recovery_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE analysis_runs ALTER COLUMN pipeline_version SET DEFAULT 'inference_v3_3';
