-- Re-analyze every latest accessible revision whose current result predates inference v4.
-- Jobs use backfill priority, so live collection keeps leasing first. Each finished v4 run
-- marks the earlier result of its revision as superseded.
INSERT INTO analysis_jobs (post_revision_id, priority, trigger_kind)
SELECT run.post_revision_id, 'backfill', 'manual'
FROM analysis_runs AS run
JOIN post_revisions AS revision ON revision.id = run.post_revision_id
JOIN raw_posts AS post ON post.id = revision.raw_post_id
WHERE run.status IN (
        'completed', 'completed_with_partial_classification', 'completed_with_entity_fallback'
    )
  AND run.pipeline_version <> 'inference_v4'
  AND post.deleted_at IS NULL
  AND post.inaccessible_at IS NULL
  AND revision.id = (
      SELECT latest.id FROM post_revisions AS latest
      WHERE latest.raw_post_id = post.id
      ORDER BY latest.revision_number DESC
      LIMIT 1
  )
ON CONFLICT DO NOTHING;
