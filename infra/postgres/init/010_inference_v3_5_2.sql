ALTER TABLE analysis_runs ALTER COLUMN pipeline_version SET DEFAULT 'inference_v3_5_2';

INSERT INTO entity_aliases (entity_id, alias, normalized_alias)
SELECT id, 'ЧЕСНО', 'чесно'
FROM registry_entities
WHERE canonical_name = 'Рух ЧЕСНО'
ON CONFLICT (entity_id, alias) DO NOTHING;
