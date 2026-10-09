-- Inference v3.6 re-analyses already analyzed revisions. A newer completed run supersedes the
-- previous completed run of the same revision so analytics never count both.
ALTER TABLE analysis_runs DROP CONSTRAINT IF EXISTS analysis_runs_status_check;
ALTER TABLE analysis_runs ADD CONSTRAINT analysis_runs_status_check CHECK (status IN (
    'running', 'retry_scheduled', 'completed', 'completed_with_partial_classification',
    'completed_with_entity_fallback', 'failed', 'filtered_out', 'superseded'
));

ALTER TABLE analysis_runs ALTER COLUMN pipeline_version SET DEFAULT 'inference_v3_6';
