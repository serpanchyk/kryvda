ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS retry_round INTEGER NOT NULL DEFAULT 0;

ALTER TABLE analysis_jobs DROP CONSTRAINT IF EXISTS analysis_jobs_status_check;
ALTER TABLE analysis_jobs ADD CONSTRAINT analysis_jobs_status_check CHECK (status IN (
    'pending', 'leased', 'retry_scheduled', 'completed', 'failed', 'skipped'
));

ALTER TABLE analysis_runs DROP CONSTRAINT IF EXISTS analysis_runs_status_check;
ALTER TABLE analysis_runs ADD CONSTRAINT analysis_runs_status_check CHECK (status IN (
    'running', 'retry_scheduled', 'completed', 'completed_with_partial_classification',
    'completed_with_entity_fallback', 'failed', 'filtered_out'
));

DROP INDEX IF EXISTS analysis_jobs_active_revision_idx;
CREATE UNIQUE INDEX analysis_jobs_active_revision_idx ON analysis_jobs (post_revision_id)
WHERE status IN ('pending', 'leased', 'retry_scheduled');

WITH ranked_failures AS (
    SELECT failed.id,
           ROW_NUMBER() OVER (
               PARTITION BY failed.post_revision_id ORDER BY failed.id DESC
           ) AS recovery_rank
    FROM analysis_jobs AS failed
    WHERE failed.status = 'failed'
      AND NOT EXISTS (
          SELECT 1
          FROM analysis_jobs AS successor
          WHERE successor.post_revision_id = failed.post_revision_id
            AND successor.id <> failed.id
            AND successor.status IN ('completed', 'pending', 'leased', 'retry_scheduled')
      )
), recovered_jobs AS (
    UPDATE analysis_jobs AS job
    SET status = 'retry_scheduled',
        available_at = now() + (
            300 + ((job.id * 2654435761) % 31)
        ) * interval '1 second',
        leased_until = NULL,
        retry_round = 1,
        completed_at = NULL,
        updated_at = now()
    FROM ranked_failures AS candidate
    WHERE job.id = candidate.id AND candidate.recovery_rank = 1
    RETURNING job.id
)
UPDATE analysis_runs AS run
SET status = 'retry_scheduled', completed_at = NULL
FROM recovered_jobs
WHERE run.job_id = recovered_jobs.id;
