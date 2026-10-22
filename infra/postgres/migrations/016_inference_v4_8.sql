-- Inference v4.8 adds the affiliations pass: it names the organizations a post links each person
-- to, so a negative stance toward a head, member or former employee also counts for the
-- organization.
ALTER TABLE analysis_runs ALTER COLUMN pipeline_version SET DEFAULT 'inference_v4_8';

ALTER TABLE inference_pass_attempts DROP CONSTRAINT IF EXISTS inference_pass_attempts_pass_name_check;
ALTER TABLE inference_pass_attempts ADD CONSTRAINT inference_pass_attempts_pass_name_check
    CHECK (pass_name IN (
        'candidates', 'entities', 'claims', 'targets', 'classification', 'affiliations'
    ));
ALTER TABLE inference_pass_diagnostics
    DROP CONSTRAINT IF EXISTS inference_pass_diagnostics_pass_name_check;
ALTER TABLE inference_pass_diagnostics ADD CONSTRAINT inference_pass_diagnostics_pass_name_check
    CHECK (pass_name IN (
        'candidates', 'entities', 'claims', 'targets', 'classification', 'affiliations'
    ));
