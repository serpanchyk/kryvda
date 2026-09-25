"""API health, avatar, registry, and candidate endpoint tests."""

from pathlib import Path

from httpx import ASGITransport, AsyncClient
from telegram_monitor_api import main
from telegram_monitor_api.main import ApiSettings, app, create_app


async def test_health_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "telegram-monitor-api"}


async def test_api_allows_local_frontend_origin() -> None:
    """The browser frontend can read API responses from its Compose port."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


class FakePool:
    async def fetchval(self, query: str, channel_id: int) -> str | None:
        return "image/jpeg" if channel_id == 1 else None

    async def close(self) -> None:
        return None


class AnalysisHealthPool(FakePool):
    """Return an inspectable queue and run snapshot."""

    async def fetchrow(self, query: str) -> dict[str, object]:
        if "FROM analysis_jobs" in query:
            return {
                "pending_live": 2,
                "pending_backfill": 5,
                "leased": 1,
                "failed": 3,
                "oldest_pending_seconds": 12.0,
            }
        return {
            "last_completed_at": "2026-09-20T10:00:00Z",
            "completed_last_hour": 8,
            "failed_last_hour": 1,
            "partial_last_hour": 2,
        }


async def fake_create_pool(_: str) -> FakePool:
    return FakePool()


async def fake_analysis_health_pool(_: str) -> AnalysisHealthPool:
    return AnalysisHealthPool()


async def test_analysis_health_endpoint(monkeypatch: object) -> None:
    monkeypatch.setattr(main.asyncpg, "create_pool", fake_analysis_health_pool)  # type: ignore[union-attr]
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/analysis/health")
    assert response.status_code == 200
    assert response.json() == {
        "jobs": {
            "pending_live": 2,
            "pending_backfill": 5,
            "leased": 1,
            "failed": 3,
            "oldest_pending_seconds": 12.0,
        },
        "runs": {
            "last_completed_at": "2026-09-20T10:00:00Z",
            "completed_last_hour": 8,
            "failed_last_hour": 1,
            "partial_last_hour": 2,
        },
    }


class FakeAnalytics:
    """Return API-shaped analytical data without a PostgreSQL dependency."""

    last_entity_args: tuple[object, ...] | None = None
    last_evidence_args: tuple[object, ...] | None = None

    def __init__(self, pool: object) -> None:
        self.pool = pool

    async def dashboard(self, start: object, end: object) -> dict[str, object]:
        return {"entities": [{"id": 1}], "channels": [{"id": 2}]}

    async def entity(
        self,
        entity_id: int,
        channel_id: object,
        start: object,
        end: object,
        limit: int,
        offset: int,
    ) -> dict[str, object] | None:
        type(self).last_entity_args = (entity_id, channel_id, start, end, limit, offset)
        return {
            "entity": {"id": entity_id},
            "summary": {},
            "channels": {
                "items": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
            },
            "incomplete_posts": 1,
            "rhetoric": [],
        }

    async def evidence(
        self,
        entity_id: int,
        channel_id: object,
        stance: object,
        rhetoric: object,
        epistemic_status: object,
        source_kind: object,
        start: object,
        end: object,
        limit: int,
        offset: int,
    ) -> dict[str, object]:
        type(self).last_evidence_args = (
            entity_id,
            channel_id,
            stance,
            rhetoric,
            epistemic_status,
            source_kind,
            start,
            end,
            limit,
            offset,
        )
        return {
            "items": [{"claim_id": 3, "entity_id": entity_id, "stance": stance}],
            "total": 1,
            "limit": limit,
            "offset": offset,
        }

    async def channels(
        self,
        start: object,
        end: object,
        limit: int,
        offset: int,
    ) -> dict[str, object]:
        return {
            "items": [{"id": 2, "title": "Channel"}],
            "daily": [],
            "total": 1,
            "limit": limit,
            "offset": offset,
        }

    async def channel(
        self,
        channel_id: int,
        start: object,
        end: object,
        limit: int,
        offset: int,
    ) -> dict[str, object] | None:
        type(self).last_channel_args = (channel_id, start, end, limit, offset)
        return None if channel_id == 404 else {"channel": {"id": channel_id}}

    async def claims(self, *args: object) -> dict[str, object]:
        type(self).last_claim_args = args
        return {"items": [], "total": 0, "limit": 25, "offset": 0}

    async def post(self, post_id: int) -> dict[str, object] | None:
        return {"id": post_id, "content": "Evidence"}


async def test_read_only_investigation_endpoints(monkeypatch: object) -> None:
    monkeypatch.setattr(main.asyncpg, "create_pool", fake_create_pool)  # type: ignore[union-attr]
    monkeypatch.setattr(main, "AnalyticsRepository", FakeAnalytics)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/dashboard")).json()["entities"] == [{"id": 1}]
        assert (
            await client.get(
                "/entities/4/analytics", params={"channel_id": 7, "limit": 0, "offset": -1}
            )
        ).json()["incomplete_posts"] == 1
        assert FakeAnalytics.last_entity_args == (4, 7, None, None, 1, 0)
        evidence = await client.get(
            "/entities/4/evidence",
            params={
                "stance": "негативне",
                "rhetoric": "делегітимізація",
                "epistemic_status": "питання",
                "source_kind": "named_entity",
                "limit": 0,
                "offset": -1,
            },
        )
        assert FakeAnalytics.last_evidence_args == (
            4,
            None,
            "негативне",
            "делегітимізація",
            "питання",
            "named_entity",
            None,
            None,
            1,
            0,
        )
        assert evidence.json()["items"][0]["claim_id"] == 3
        invalid_rhetoric = await client.get("/entities/4/evidence", params={"rhetoric": "invalid"})
        assert invalid_rhetoric.status_code == 422
        assert (await client.get("/channels")).json()["items"][0]["title"] == "Channel"
        assert (await client.get("/channels/3/analytics", params={"limit": 0})).json()["channel"][
            "id"
        ] == 3
        assert FakeAnalytics.last_channel_args == (3, None, None, 1, 0)
        assert (await client.get("/channels/404/analytics")).status_code == 404
        assert (
            await client.get(
                "/claims",
                params={
                    "rhetoric": "делегітимізація",
                    "epistemic_status": "питання",
                    "source_kind": "named_entity",
                },
            )
        ).json() == {"items": [], "total": 0, "limit": 25, "offset": 0}
        assert FakeAnalytics.last_claim_args[4:7] == (
            "делегітимізація",
            "питання",
            "named_entity",
        )
        assert (await client.get("/posts/7")).json()["content"] == "Evidence"


async def test_channel_image_serves_stored_avatar(tmp_path: Path, monkeypatch: object) -> None:
    (tmp_path / "1.avatar").write_bytes(b"\xff\xd8\xffavatar")
    monkeypatch.setattr(main.asyncpg, "create_pool", fake_create_pool)  # type: ignore[union-attr]
    transport = ASGITransport(app=create_app(ApiSettings(channel_image_storage_path=tmp_path)))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/channel-images/1")
    assert response.status_code == 200
    assert response.content == b"\xff\xd8\xffavatar"
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-cache"


async def test_channel_image_returns_not_found_without_metadata(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setattr(main.asyncpg, "create_pool", fake_create_pool)  # type: ignore[union-attr]
    transport = ASGITransport(app=create_app(ApiSettings(channel_image_storage_path=tmp_path)))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/channel-images/2")
    assert response.status_code == 404


class FakeRegistry:
    """Return deterministic registry API results."""

    def __init__(self, pool: object) -> None:
        self.pool = pool

    async def list_entities(self, *args: object) -> dict[str, object]:
        return {"items": [{"id": 1}], "total": 1, "limit": 25, "offset": 0}

    async def create_entity(
        self, name: str, kind: str, aliases: list[str], monitored: bool
    ) -> tuple[int, int]:
        return 4, 2

    async def update_entity(
        self, entity_id: int, name: str | None, kind: str | None, monitored: bool | None
    ) -> int | None:
        return 3

    async def add_alias(self, entity_id: int, alias: str) -> int | None:
        return 1

    async def list_candidates(self, status: str) -> list[dict[str, object]]:
        return [{"id": 8, "status": status}]

    async def link_candidate(self, candidate_id: int, entity_id: int) -> int | None:
        return 1

    async def ignore_candidate(self, candidate_id: int) -> bool:
        return True

    async def list_alias_candidates(self, entity_id: int) -> list[dict[str, object]]:
        return [{"id": 9}]

    async def review_alias_candidate(self, candidate_id: int, approve: bool) -> int | None:
        return 2 if approve else 0


async def test_registry_and_candidate_admin_endpoints(monkeypatch: object) -> None:
    monkeypatch.setattr(main.asyncpg, "create_pool", fake_create_pool)  # type: ignore[union-attr]
    monkeypatch.setattr(main, "RegistryRepository", FakeRegistry)  # type: ignore[union-attr]
    transport = ASGITransport(app=create_app())
    entity = {
        "canonical_name": "Шабунін",
        "coarse_type": "person",
        "aliases": ["Віталій Шабунін"],
        "monitored": True,
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/entities?monitored=true")).json()["items"][0]["id"] == 1
        assert (await client.post("/entities", json=entity)).json()["backfill_jobs_enqueued"] == 2
        assert (await client.patch("/entities/4", json={"monitored": True})).json()[
            "backfill_jobs_enqueued"
        ] == 3
        alias_response = await client.post("/entities/4/aliases", json={"alias": "Шабунін"})
        assert alias_response.status_code == 201
        assert (await client.get("/entity-candidates")).json()[0]["status"] == "pending"
        link = await client.post("/entity-candidates/8/link", json={"entity_id": 4})
        assert link.json() == {"linked": True, "backfill_jobs_enqueued": 1}
        create = await client.post("/entity-candidates/8/create-entity", json=entity)
        assert create.status_code == 201
        assert (await client.post("/entity-candidates/8/ignore")).json() == {"ignored": True}
        assert (await client.get("/entities/4/alias-candidates")).json() == [{"id": 9}]
        assert (await client.post("/alias-candidates/9/approve")).json()[
            "backfill_jobs_enqueued"
        ] == 2
        assert (await client.post("/alias-candidates/9/ignore")).json()[
            "backfill_jobs_enqueued"
        ] == 0
