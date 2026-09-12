DROP TABLE IF EXISTS post_analysis_extractions;
DROP TABLE IF EXISTS analysis_jobs;

\ir ../init/002_inference_v3.sql
\ir ../init/003_registry_seed.sql

INSERT INTO analysis_jobs (post_revision_id, priority, trigger_kind)
SELECT latest.id, 'backfill', 'entity_created'
FROM (
    SELECT DISTINCT ON (post.id) revision.id, revision.content
    FROM raw_posts AS post
    JOIN post_revisions AS revision ON revision.raw_post_id = post.id
    WHERE post.deleted_at IS NULL AND post.inaccessible_at IS NULL
    ORDER BY post.id, revision.revision_number DESC
) AS latest
WHERE EXISTS (
    SELECT 1 FROM entity_aliases AS alias
    JOIN registry_entities AS entity ON entity.id = alias.entity_id
    WHERE entity.monitored
      AND position(alias.normalized_alias IN lower(latest.content)) > 0
)
ON CONFLICT DO NOTHING;
