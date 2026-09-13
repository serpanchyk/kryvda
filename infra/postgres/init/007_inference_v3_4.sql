ALTER TABLE inference_pass_attempts
    DROP CONSTRAINT IF EXISTS inference_pass_attempts_run_id_pass_name_attempt_kind_key;

ALTER TABLE inference_pass_attempts DROP CONSTRAINT IF EXISTS inference_pass_attempts_attempt_kind_check;
ALTER TABLE inference_pass_attempts ADD CONSTRAINT inference_pass_attempts_attempt_kind_check CHECK (
    attempt_kind IN ('primary', 'repair', 'retry', 'batch_primary', 'batch_retry', 'individual_retry')
);

ALTER TABLE analysis_runs ALTER COLUMN pipeline_version SET DEFAULT 'inference_v3_4';
