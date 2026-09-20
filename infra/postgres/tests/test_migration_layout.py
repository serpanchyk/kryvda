"""Static safety checks for the Compose-managed PostgreSQL migration layout."""

from pathlib import Path

POSTGRES_ROOT = Path("infra/postgres")


def test_fresh_initialization_records_current_inference_baseline() -> None:
    """Avoid replaying the destructive legacy transition on a fresh volume."""
    content = (POSTGRES_ROOT / "init" / "011_schema_migrations.sql").read_text()

    for version in range(3, 12):
        assert f"'{version:03d}_" in content


def test_migration_runner_only_applies_v3_transition_to_legacy_schema() -> None:
    """Require the registry schema to be absent before running migration 003."""
    content = (POSTGRES_ROOT / "migrate.sql").read_text()

    assert "to_regclass('public.registry_entities') IS NULL" in content
    assert "to_regclass('public.inference_pass_attempts') IS NULL" in content
    assert "pg_advisory_xact_lock" in content
    assert "\\i /database/migrations/003_inference_v3.sql" in content
    assert "\\i /database/migrations/010_inference_v3_5_2.sql" in content
    assert "\\i /database/migrations/011_repair_inference_pass_attempts_unique.sql" in content


def test_v3_base_schema_can_retain_partial_transition_registry() -> None:
    """Allow migration 003 to rebuild analysis tables without dropping registry data."""
    content = (POSTGRES_ROOT / "init" / "002_inference_v3.sql").read_text()

    assert "CREATE TABLE IF NOT EXISTS registry_entities" in content
    assert "CREATE TABLE IF NOT EXISTS inference_pass_attempts" in content
