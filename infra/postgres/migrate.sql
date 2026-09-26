\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

BEGIN;
SELECT pg_advisory_xact_lock(94615230);

SELECT CASE
    WHEN EXISTS (
        SELECT 1 FROM schema_migrations WHERE version = '003_inference_v3.sql'
    ) THEN false
    WHEN to_regclass('public.registry_entities') IS NULL
        OR to_regclass('public.inference_pass_attempts') IS NULL THEN true
    ELSE false
END AS apply_003 \gset

\if :apply_003
\i /database/migrations/003_inference_v3.sql
INSERT INTO schema_migrations (version) VALUES ('003_inference_v3.sql');
\else
INSERT INTO schema_migrations (version)
VALUES ('003_inference_v3.sql') ON CONFLICT (version) DO NOTHING;
\endif

SELECT NOT EXISTS (
    SELECT 1 FROM schema_migrations WHERE version = '004_inference_v3_1.sql'
) AS apply_004 \gset
\if :apply_004
\i /database/migrations/004_inference_v3_1.sql
INSERT INTO schema_migrations (version) VALUES ('004_inference_v3_1.sql');
\endif

SELECT NOT EXISTS (
    SELECT 1 FROM schema_migrations WHERE version = '005_inference_v3_2.sql'
) AS apply_005 \gset
\if :apply_005
\i /database/migrations/005_inference_v3_2.sql
INSERT INTO schema_migrations (version) VALUES ('005_inference_v3_2.sql');
\endif

SELECT NOT EXISTS (
    SELECT 1 FROM schema_migrations WHERE version = '006_inference_v3_3.sql'
) AS apply_006 \gset
\if :apply_006
\i /database/migrations/006_inference_v3_3.sql
INSERT INTO schema_migrations (version) VALUES ('006_inference_v3_3.sql');
\endif

SELECT NOT EXISTS (
    SELECT 1 FROM schema_migrations WHERE version = '007_inference_v3_4.sql'
) AS apply_007 \gset
\if :apply_007
\i /database/migrations/007_inference_v3_4.sql
INSERT INTO schema_migrations (version) VALUES ('007_inference_v3_4.sql');
\endif

SELECT NOT EXISTS (
    SELECT 1 FROM schema_migrations WHERE version = '008_inference_v3_5.sql'
) AS apply_008 \gset
\if :apply_008
\i /database/migrations/008_inference_v3_5.sql
INSERT INTO schema_migrations (version) VALUES ('008_inference_v3_5.sql');
\endif

SELECT NOT EXISTS (
    SELECT 1 FROM schema_migrations WHERE version = '009_inference_v3_5_1.sql'
) AS apply_009 \gset
\if :apply_009
\i /database/migrations/009_inference_v3_5_1.sql
INSERT INTO schema_migrations (version) VALUES ('009_inference_v3_5_1.sql');
\endif

SELECT NOT EXISTS (
    SELECT 1 FROM schema_migrations WHERE version = '010_inference_v3_5_2.sql'
) AS apply_010 \gset
\if :apply_010
\i /database/migrations/010_inference_v3_5_2.sql
INSERT INTO schema_migrations (version) VALUES ('010_inference_v3_5_2.sql');
\endif

SELECT NOT EXISTS (
    SELECT 1 FROM schema_migrations WHERE version = '011_repair_inference_pass_attempts_unique.sql'
) AS apply_011 \gset
\if :apply_011
\i /database/migrations/011_repair_inference_pass_attempts_unique.sql
INSERT INTO schema_migrations (version) VALUES ('011_repair_inference_pass_attempts_unique.sql');
\endif

SELECT NOT EXISTS (
    SELECT 1 FROM schema_migrations WHERE version = '012_scheduled_analysis_retries.sql'
) AS apply_012 \gset
\if :apply_012
\i /database/migrations/012_scheduled_analysis_retries.sql
INSERT INTO schema_migrations (version) VALUES ('012_scheduled_analysis_retries.sql');
\endif

COMMIT;
