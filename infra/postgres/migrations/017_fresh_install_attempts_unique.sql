-- Fresh volumes record migration 011 as applied but never ran it, so they lacked the unique
-- index every inference attempt upsert relies on; recreate it wherever it is missing.
CREATE UNIQUE INDEX IF NOT EXISTS inference_pass_attempts_run_pass_attempt_kind_key
    ON inference_pass_attempts (run_id, pass_name, attempt_kind);
