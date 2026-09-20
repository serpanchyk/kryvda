from datetime import UTC, datetime

from monitoring_common.contracts import matched_registry_entity_ids
from registry_post_coverage import PreparedRegistryMatcher, build_summary, coverage_records


def test_coverage_counts_each_post_once_per_matching_entity() -> None:
    entities = [
        {"id": 1, "canonical_name": "Анна", "coarse_type": "person", "monitored": True},
        {"id": 2, "canonical_name": "ЦПК", "coarse_type": "organization", "monitored": True},
    ]
    aliases = [
        {**entities[0], "entity_id": 1, "alias": "Анна", "normalized_alias": "анна"},
        {**entities[0], "entity_id": 1, "alias": "Анну", "normalized_alias": "анну"},
        {**entities[1], "entity_id": 2, "alias": "ЦПК", "normalized_alias": "цпк"},
    ]

    records, scanned, matched = coverage_records(
        ["Анна й Анну згадали разом", "ЦПК згадує Анна", "нічого"], entities, aliases
    )

    assert scanned == 3
    assert matched == 2
    assert records == [
        {
            "entity_id": 1,
            "canonical_name": "Анна",
            "coarse_type": "person",
            "matched_post_count": 2,
        },
        {
            "entity_id": 2,
            "canonical_name": "ЦПК",
            "coarse_type": "organization",
            "matched_post_count": 1,
        },
    ]


def test_prepared_matcher_matches_production_policy() -> None:
    aliases = [
        {
            "entity_id": 1,
            "canonical_name": "Віталій Шабунін",
            "coarse_type": "person",
            "monitored": True,
            "alias": "Віталій Шабунін",
            "normalized_alias": "віталій шабунін",
        },
        {
            "entity_id": 2,
            "canonical_name": "Рух ЧЕСНО",
            "coarse_type": "organization",
            "monitored": True,
            "alias": "ЧЕСНО",
            "normalized_alias": "чесно",
        },
    ]
    matcher = PreparedRegistryMatcher(aliases)

    for content in ("Шабуніну вручили лист", "Рух ЧЕСНО виступив", "чесно кажучи"):
        assert matcher.matched_entity_ids(content) == matched_registry_entity_ids(content, aliases)


def test_summary_calculates_eta_from_completed_runs() -> None:
    started = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
    summary = build_summary(
        generated_at=datetime(2026, 9, 20, 11, 0, tzinfo=UTC),
        active_entities=2,
        approved_aliases=3,
        latest_posts_scanned=10,
        posts_matching_any_entity=4,
        queue_statuses={"pending": 100, "leased": 20, "completed": 5},
        completed_runs=30,
        first_started_at=started,
        last_completed_at=datetime(2026, 9, 20, 10, 10, tzinfo=UTC),
        average_seconds_per_post=20.0,
    )

    throughput = summary["throughput_since_repair"]
    assert throughput["remaining_pending_or_leased_jobs"] == 120
    assert throughput["observed_jobs_per_second"] == 0.05
    assert throughput["estimated_remaining_seconds"] == 2400.0


def test_summary_has_no_eta_without_completed_time_window() -> None:
    summary = build_summary(
        generated_at=datetime(2026, 9, 20, 11, 0, tzinfo=UTC),
        active_entities=1,
        approved_aliases=1,
        latest_posts_scanned=1,
        posts_matching_any_entity=1,
        queue_statuses={"pending": 1},
        completed_runs=0,
        first_started_at=None,
        last_completed_at=None,
        average_seconds_per_post=None,
    )

    assert summary["throughput_since_repair"]["estimated_remaining_seconds"] is None
