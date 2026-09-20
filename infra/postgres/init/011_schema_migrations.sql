CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations (version)
VALUES
    ('003_inference_v3.sql'),
    ('004_inference_v3_1.sql'),
    ('005_inference_v3_2.sql'),
    ('006_inference_v3_3.sql'),
    ('007_inference_v3_4.sql'),
    ('008_inference_v3_5.sql'),
    ('009_inference_v3_5_1.sql'),
    ('010_inference_v3_5_2.sql'),
    ('011_repair_inference_pass_attempts_unique.sql')
ON CONFLICT (version) DO NOTHING;
