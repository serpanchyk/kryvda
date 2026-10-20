-- Inference v3.7 lets Pass 1 confirm or reject each registry alias match; new runs record it.
ALTER TABLE analysis_runs ALTER COLUMN pipeline_version SET DEFAULT 'inference_v3_7';

-- The candidate pass confirms or rejects registry alias matches, and a broken primary output can
-- be salvaged from its complete parts without a repair call.
ALTER TABLE inference_pass_attempts DROP CONSTRAINT IF EXISTS inference_pass_attempts_pass_name_check;
ALTER TABLE inference_pass_attempts ADD CONSTRAINT inference_pass_attempts_pass_name_check
    CHECK (pass_name IN ('candidates', 'entities', 'claims', 'classification'));
ALTER TABLE inference_pass_diagnostics
    DROP CONSTRAINT IF EXISTS inference_pass_diagnostics_pass_name_check;
ALTER TABLE inference_pass_diagnostics ADD CONSTRAINT inference_pass_diagnostics_pass_name_check
    CHECK (pass_name IN ('candidates', 'entities', 'claims', 'classification'));
ALTER TABLE inference_pass_diagnostics
    DROP CONSTRAINT IF EXISTS inference_pass_diagnostics_final_validation_status_check;
ALTER TABLE inference_pass_diagnostics
    ADD CONSTRAINT inference_pass_diagnostics_final_validation_status_check
    CHECK (final_validation_status IN (
        'valid', 'invalid', 'generation_failure', 'degraded', 'partial', 'salvaged'
    ));

INSERT INTO schema_migrations (version)
VALUES ('014_inference_v3_7.sql')
ON CONFLICT (version) DO NOTHING;
