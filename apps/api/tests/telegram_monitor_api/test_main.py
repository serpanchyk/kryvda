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


class FakePool:
    async def fetchval(self, query: str, channel_id: int) -> str | None:
        return "image/jpeg" if channel_id == 1 else None

    async def close(self) -> None:
        return None


async def fake_create_pool(_: str) -> FakePool:
    return FakePool()


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

    async def list_entities(self, monitored: bool | None) -> list[dict[str, object]]:
        return [{"id": 1, "monitored": monitored}]

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
        assert (await client.get("/entities?monitored=true")).json()[0]["id"] == 1
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
