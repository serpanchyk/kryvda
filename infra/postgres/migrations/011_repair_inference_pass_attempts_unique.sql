CREATE UNIQUE INDEX IF NOT EXISTS inference_pass_attempts_run_pass_attempt_kind_key
    ON inference_pass_attempts (run_id, pass_name, attempt_kind);
