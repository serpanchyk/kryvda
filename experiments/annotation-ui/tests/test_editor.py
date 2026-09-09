"""Exercise draft recovery, revision immutability and completion validation."""

import json
from typing import Any

from annotation_app import create_app
from fastapi.testclient import TestClient


class ReadOnlyTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: Any) -> None:
        return None


class SourceConnection:
    def __init__(self) -> None:
        self.closed = False
        self.queries: list[tuple[str, tuple[Any, ...]]] = []

    def transaction(self, *, readonly: bool) -> ReadOnlyTransaction:
        assert readonly is True
        return ReadOnlyTransaction()

    async def fetch(self, query: str, *args: Any, timeout: int) -> list[dict[str, Any]]:
        assert query.startswith("SELECT")
        self.queries.append((query, args))
        return [
            {
                "post_revision_id": 9,
                "raw_post_id": 3,
                "channel_id": 1,
                "channel_reference": "test",
                "telegram_message_id": 22,
                "published_at": "2026-09-08 12:30:00+00",
                "text": "😀 ЦПК",
            }
        ]

    async def close(self) -> None:
        self.closed = True


def test_source_snapshot_registry_and_completion(tmp_path, monkeypatch):
    connection = SourceConnection()

    async def connect(dsn: str, timeout: int) -> SourceConnection:
        return connection

    monkeypatch.setenv("ANNOTATION_POSTGRES_DSN", "postgresql://test")
    monkeypatch.setattr("annotation_app.asyncpg.connect", connect)
    client = TestClient(create_app(tmp_path))
    posts = client.get("/api/posts?q=ЦПК&channel=1&before=20").json()
    assert posts[0]["published_at"] == "2026-09-08T12:30:00+00:00"
    assert connection.closed
    assert connection.queries[0][1][:3] == (20, "ЦПК", 1)
    item = client.post("/api/start/9").json()
    assert client.post("/api/start/9").json() == item
    registry = client.post(
        "/api/registry",
        json={"canonical_name": "ЦПК", "surface_form": "ЦПК", "entity_type": "organization"},
    ).json()
    item["record"]["selection"] = {
        "facets": ["entity"],
        "reason": "Test",
        "is_keyword_false_positive": False,
    }
    entity = {
        "id": "e1",
        "mention_span": {"start": 2, "end": 5},
        "surface_form": "ЦПК",
        "canonical_name": registry["canonical_name"],
        "registry_entity_id": registry["id"],
        "entity_type": "organization",
        "registry_status": "candidate",
        "resolution_source": "registry",
        "subject_role": "primary",
    }
    item["record"]["annotations"]["entities"] = [entity]
    item["status"] = "completed"
    response = client.put("/api/records/9", json=item)
    assert response.status_code == 200, response.text
    assert json.loads((tmp_path / "annotations.jsonl").read_text())["source"] == posts[0]
    recovered = TestClient(create_app(tmp_path)).get("/api/state").json()
    assert recovered["registry"][0] == registry
    assert recovered["records"]["9"]["status"] == "completed"


def test_malformed_completion_retains_draft(tmp_path, monkeypatch):
    connection = SourceConnection()

    async def connect(dsn: str, timeout: int) -> SourceConnection:
        return connection

    monkeypatch.setenv("ANNOTATION_POSTGRES_DSN", "postgresql://test")
    monkeypatch.setattr("annotation_app.asyncpg.connect", connect)
    client = TestClient(create_app(tmp_path))
    item = client.post("/api/start/9").json()
    item["record"]["annotations"] = None
    item["status"] = "completed"
    assert client.put("/api/records/9", json=item).status_code == 422
    assert client.get("/api/state").json()["records"]["9"]["version"] == 1


def test_import_preview_is_unsaved_and_confirmation_creates_candidate(tmp_path, monkeypatch):
    connection = SourceConnection()

    async def connect(dsn: str, timeout: int) -> SourceConnection:
        return connection

    monkeypatch.setenv("ANNOTATION_POSTGRES_DSN", "postgresql://test")
    monkeypatch.setattr("annotation_app.asyncpg.connect", connect)
    client = TestClient(create_app(tmp_path))
    item = client.post("/api/start/9").json()
    payload = {
        "selection": {
            "facets": ["entity"],
            "reason": "Перевірка candidate",
            "is_keyword_false_positive": False,
        },
        "annotations": {
            "entities": [
                {
                    "id": "e1",
                    "mention_span": {"start": 2, "end": 5},
                    "surface_form": "ЦПК",
                    "canonical_name": " Центр протидії корупції ",
                    "entity_type": "organization",
                    "subject_role": "primary",
                }
            ],
            "stances": [],
            "claims": [],
            "rhetorical_features": [],
        },
    }
    preview = client.post(
        "/api/records/9/import-preview", json={"version": item["version"], "payload": payload}
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["record"]["annotations"]["entities"][0]["registry_entity_id"] == "local-1"
    assert preview.json()["candidates"][0]["canonical_name"] == "Центр протидії корупції"
    assert client.get("/api/state").json()["registry"] == []
    assert client.get("/api/state").json()["records"]["9"]["version"] == 1
    completed = client.post(
        "/api/records/9/complete-import", json={"version": item["version"], "payload": payload}
    )
    assert completed.status_code == 200, completed.text
    state = client.get("/api/state").json()
    assert state["records"]["9"]["status"] == "completed"
    assert state["registry"][0]["aliases"] == ["ЦПК"]


def test_import_rejects_false_positive_with_annotations(tmp_path, monkeypatch):
    connection = SourceConnection()

    async def connect(dsn: str, timeout: int) -> SourceConnection:
        return connection

    monkeypatch.setenv("ANNOTATION_POSTGRES_DSN", "postgresql://test")
    monkeypatch.setattr("annotation_app.asyncpg.connect", connect)
    client = TestClient(create_app(tmp_path))
    item = client.post("/api/start/9").json()
    payload = {
        "selection": {
            "facets": ["false_positive"],
            "reason": "Шум",
            "is_keyword_false_positive": True,
        },
        "annotations": {"entities": [], "stances": [], "claims": [], "rhetorical_features": []},
    }
    payload["annotations"]["entities"].append(
        {
            "id": "e1",
            "mention_span": {"start": 2, "end": 5},
            "surface_form": "ЦПК",
            "canonical_name": None,
            "entity_type": "organization",
            "subject_role": "primary",
        }
    )
    response = client.post(
        "/api/records/9/import-preview", json={"version": item["version"], "payload": payload}
    )
    assert response.status_code == 422
    assert "False-positive examples" in response.text


def test_draft_snapshot_and_finalize(tmp_path):
    record = {
        "example_id": "golden_v0-001",
        "schema_version": "annotation_schema_v1",
        "source": {
            "channel_id": 1,
            "channel_reference": "test",
            "raw_post_id": 1,
            "post_revision_id": 1,
            "telegram_message_id": 1,
            "published_at": "2026-09-08T00:00:00Z",
            "text": "Текст 😀",
        },
        "selection": {
            "facets": ["control"],
            "reason": "Контроль",
            "is_keyword_false_positive": True,
        },
        "annotations": {"entities": [], "stances": [], "claims": [], "rhetorical_features": []},
    }
    item = {"record": record, "version": 1, "status": "draft"}
    (tmp_path / "editor.json").write_text(json.dumps({"records": {"1": item}, "registry": []}))
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/state").json()["records"]["1"]["record"] == record
    item["status"] = "completed"
    assert client.put("/api/records/1", json=item).status_code == 200
    assert json.loads((tmp_path / "annotations.jsonl").read_text()) == record
    assert client.put("/api/records/1", json=item).status_code == 409
    item["version"] = 2
    record["source"]["text"] = "changed"
    assert client.put("/api/records/1", json=item).status_code == 422


def test_missing_database_keeps_editor_available(tmp_path, monkeypatch):
    monkeypatch.delenv("ANNOTATION_POSTGRES_DSN", raising=False)
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/posts").status_code == 503
    assert client.get("/api/schema").status_code == 200
    assert client.get("/api/state").json() == {"records": {}, "registry": []}


def test_launcher_passes_credentials_via_environment(tmp_path, monkeypatch):
    import launch_editor

    script = tmp_path / "workspace/experiments/annotation-ui/src/launch_editor.py"
    script.parent.mkdir(parents=True)
    (tmp_path / "workspace").mkdir(exist_ok=True)
    monkeypatch.setattr(launch_editor, "__file__", str(script))
    monkeypatch.delenv("ANNOTATION_POSTGRES_DSN", raising=False)
    (tmp_path / "workspace/.env").write_text("POSTGRES_PORT=5433\nPOSTGRES_PASSWORD=a@b\n")
    calls = []
    monkeypatch.setattr(launch_editor.subprocess, "run", lambda *a, **k: calls.append((a, k)))
    launch_editor.main()
    args, kwargs = calls[0]
    assert "a@b" not in str(args)
    assert ":a%40b@postgres:5432/" in kwargs["env"]["ANNOTATION_POSTGRES_DSN"]
    assert kwargs["check"] is True
