"""Serve the local annotation editor and persist reproducible dataset snapshots."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from golden_v0_validation import _semantic_errors, load_schema
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "datasets/golden_v0/data"
IMPORT_SCHEMA_PATH = ROOT / "datasets/golden_v0/annotation_import_schema_v1.json"


def atomic_write(path: Path, text: str) -> None:
    """Replace a file without exposing partial contents to readers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def create_app(data: Path = DATA) -> FastAPI:
    """Build a single-user editor with a read-only source database."""
    app = FastAPI()
    lock = asyncio.Lock()
    schema = load_schema()
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    import_schema = json.loads(IMPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    import_validator = Draft202012Validator(import_schema, format_checker=FormatChecker())

    def record_errors(record: dict[str, Any]) -> list[str]:
        """Collect full-record schema and semantic errors before persistence."""
        errors = [error.message for error in validator.iter_errors(record)]
        errors.extend(_semantic_errors(record, 1))
        annotations = record.get("annotations")
        if not isinstance(annotations, dict):
            return errors
        selection = record.get("selection")
        if isinstance(selection, dict) and selection.get("is_keyword_false_positive"):
            if any(annotations.values()):
                errors.append("False-positive examples must have empty annotations")
        for group in ("stances", "claims", "rhetorical_features"):
            entries = annotations.get(group, [])
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                perspective = entry.get("perspective", entry.get("attribution", {}))
                if (
                    isinstance(perspective, dict)
                    and perspective.get("source_kind") == "named_entity"
                ):
                    if not perspective.get("source_entity_id"):
                        errors.append("Named source requires an entity")
        return errors

    def registry_key(name: str, entity_type: str) -> tuple[str, str]:
        """Produce the stable candidate-match key for a resolved entity."""
        return (" ".join(name.split()).casefold(), entity_type)

    def next_registry_id(registry: list[dict[str, Any]]) -> str:
        """Allocate a local registry ID without reusing an existing entry."""
        numbers = [
            int(entry["id"].removeprefix("local-"))
            for entry in registry
            if isinstance(entry.get("id"), str) and entry["id"].removeprefix("local-").isdigit()
        ]
        return f"local-{max(numbers, default=0) + 1}"

    def materialize_import(
        state: dict[str, Any], previous: dict[str, Any], payload: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        """Freeze source fields and derive registry fields from an import payload."""
        record = {
            key: json.loads(json.dumps(previous["record"][key], ensure_ascii=False))
            for key in ("example_id", "schema_version", "source")
        }
        record["selection"] = payload["selection"]
        record["annotations"] = json.loads(json.dumps(payload["annotations"], ensure_ascii=False))
        registry = json.loads(json.dumps(state["registry"], ensure_ascii=False))
        by_key = {
            registry_key(entry["canonical_name"], entry["entity_type"]): entry for entry in registry
        }
        new_candidates: list[dict[str, Any]] = []
        for entity in record["annotations"]["entities"]:
            canonical_name = entity.pop("canonical_name")
            if canonical_name is None:
                entity.update(
                    registry_entity_id=None,
                    canonical_name=None,
                    registry_status="candidate",
                    resolution_source="unresolved",
                )
                continue
            cleaned_name = " ".join(canonical_name.split())
            key = registry_key(cleaned_name, entity["entity_type"])
            entry = by_key.get(key)
            if entry is None:
                entry = {
                    "id": next_registry_id(registry),
                    "canonical_name": cleaned_name,
                    "aliases": [entity["surface_form"]],
                    "entity_type": entity["entity_type"],
                    "status": "candidate",
                }
                registry.append(entry)
                by_key[key] = entry
                new_candidates.append(entry)
            elif entity["surface_form"] not in entry["aliases"]:
                entry["aliases"].append(entity["surface_form"])
            entity.update(
                registry_entity_id=entry["id"],
                canonical_name=entry["canonical_name"],
                registry_status=entry["status"],
                resolution_source="registry",
            )
        return record, registry, new_candidates

    def read_state() -> dict[str, Any]:
        path = data / "editor.json"
        if path.exists():
            return dict(json.loads(path.read_text(encoding="utf-8")))
        records = {}
        annotations = data / "annotations.jsonl"
        if annotations.exists():
            for line in annotations.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    record = json.loads(line)
                    records[str(record["source"]["post_revision_id"])] = {
                        "record": record,
                        "status": "completed",
                        "version": 1,
                    }
        return {"records": records, "registry": []}

    def save_state(state: dict[str, Any]) -> None:
        # editor.json is the recovery source; exports can always be regenerated.
        atomic_write(data / "editor.json", json.dumps(state, ensure_ascii=False, indent=2))
        completed = [
            item["record"] for item in state["records"].values() if item["status"] == "completed"
        ]
        completed.sort(key=lambda record: record["example_id"])
        for name, records in (
            ("annotations.jsonl", completed),
            (
                "selection_manifest.jsonl",
                [
                    {key: record[key] for key in ("example_id", "source", "selection")}
                    for record in completed
                ],
            ),
            ("entity_registry.jsonl", state["registry"]),
        ):
            atomic_write(
                data / name,
                "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            )

    async def fetch(query: str, *args: Any) -> list[dict[str, Any]]:
        dsn = os.environ.get("ANNOTATION_POSTGRES_DSN")
        if not dsn:
            raise HTTPException(503, "Set ANNOTATION_POSTGRES_DSN in the experimental .env")
        try:
            connection = await asyncpg.connect(dsn, timeout=5)
            try:
                async with connection.transaction(readonly=True):
                    rows = await connection.fetch(query, *args, timeout=10)
                    results = [dict(row) for row in rows]
                    for result in results:
                        if "published_at" in result:
                            result["published_at"] = datetime.fromisoformat(
                                result["published_at"]
                            ).isoformat()
                    return results
            finally:
                await connection.close()
        except (OSError, asyncpg.PostgresError, TimeoutError):
            raise HTTPException(503, "PostgreSQL unavailable; saved annotations remain accessible")

    @app.get("/api/schema")
    async def get_schema() -> dict[str, Any]:
        return dict(schema)

    @app.get("/api/import-schema")
    async def get_import_schema() -> dict[str, Any]:
        return dict(import_schema)

    @app.get("/api/state")
    async def get_state() -> dict[str, Any]:
        async with lock:
            return await asyncio.to_thread(read_state)

    @app.get("/api/channels")
    async def channels() -> list[dict[str, Any]]:
        return await fetch("SELECT id, title FROM monitored_channels ORDER BY id")

    @app.get("/api/posts")
    async def posts(
        q: str = "",
        channel: int | None = None,
        before: int = Query(default=9223372036854775807, gt=0),
        date_from: str = "",
        date_to: str = "",
    ) -> list[dict[str, Any]]:
        return await fetch(
            "SELECT r.id AS post_revision_id, p.id AS raw_post_id, p.channel_id, "
            "c.configured_reference AS channel_reference, p.telegram_message_id, "
            "p.published_at::text AS published_at, r.content AS text "
            "FROM post_revisions r JOIN raw_posts p ON p.id = r.raw_post_id "
            "JOIN monitored_channels c ON c.id = p.channel_id "
            "WHERE r.id < $1 AND ($2 = '' OR strpos(lower(r.content), lower($2)) > 0) "
            "AND ($3::bigint IS NULL OR p.channel_id = $3) "
            "AND ($4 = '' OR p.published_at >= NULLIF($4, '')::timestamptz) "
            "AND ($5 = '' OR p.published_at < NULLIF($5, '')::timestamptz + interval '1 day') "
            "ORDER BY r.id DESC LIMIT 30",
            before,
            q,
            channel,
            date_from,
            date_to,
        )

    @app.post("/api/start/{revision_id}")
    async def start(revision_id: int) -> dict[str, Any]:
        async with lock:
            state = await asyncio.to_thread(read_state)
            key = str(revision_id)
            if key in state["records"]:
                return dict(state["records"][key])
            rows = await fetch(
                "SELECT r.id AS post_revision_id, p.id AS raw_post_id, p.channel_id, "
                "c.configured_reference AS channel_reference, p.telegram_message_id, "
                "p.published_at::text AS published_at, r.content AS text "
                "FROM post_revisions r JOIN raw_posts p ON p.id=r.raw_post_id "
                "JOIN monitored_channels c ON c.id=p.channel_id WHERE r.id=$1",
                revision_id,
            )
            if not rows:
                raise HTTPException(404, "Revision not found")
            number = (
                max(
                    (
                        int(x["record"]["example_id"].split("-")[-1])
                        for x in state["records"].values()
                    ),
                    default=0,
                )
                + 1
            )
            if number > 999:
                raise HTTPException(409, "Pilot ID capacity reached")
            item = {
                "version": 1,
                "status": "draft",
                "record": {
                    "example_id": f"golden_v0-{number:03}",
                    "schema_version": "annotation_schema_v1",
                    "source": rows[0],
                    "selection": {"facets": [], "reason": "", "is_keyword_false_positive": False},
                    "annotations": {
                        "entities": [],
                        "stances": [],
                        "claims": [],
                        "rhetorical_features": [],
                    },
                },
            }
            state["records"][key] = item
            await asyncio.to_thread(save_state, state)
            return item

    @app.put("/api/records/{revision_id}")
    async def save(revision_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        async with lock:
            state = await asyncio.to_thread(read_state)
            previous = state["records"].get(str(revision_id))
            if previous is None:
                raise HTTPException(404, "Start the revision first")
            if payload.get("version") != previous["version"]:
                raise HTTPException(409, "Newer version exists; reload before editing")
            record = payload.get("record", {})
            if not isinstance(record, dict):
                raise HTTPException(422, "Record must be an object")
            for key in ("source", "example_id", "schema_version"):
                if record.get(key) != previous["record"][key]:
                    raise HTTPException(422, "Source snapshot and identity are immutable")
            status = payload.get("status", "draft")
            if status not in ("draft", "completed"):
                raise HTTPException(422, "Invalid status")
            if status == "completed":
                errors = record_errors(record)
                if errors:
                    raise HTTPException(422, errors)
            item = {"record": record, "status": status, "version": previous["version"] + 1}
            state["records"][str(revision_id)] = item
            await asyncio.to_thread(save_state, state)
            return item

    @app.post("/api/records/{revision_id}/import-preview")
    async def import_preview(revision_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate mutable JSON and return a full, unsaved record for review."""
        async with lock:
            state = await asyncio.to_thread(read_state)
            previous = state["records"].get(str(revision_id))
            if previous is None:
                raise HTTPException(404, "Start the revision first")
            if payload.get("version") != previous["version"]:
                raise HTTPException(409, "Newer version exists; reload before editing")
            mutable = payload.get("payload")
            if not isinstance(mutable, dict):
                raise HTTPException(422, "Import payload must be an object")
            errors = [error.message for error in import_validator.iter_errors(mutable)]
            if errors:
                raise HTTPException(422, errors)
            record, _, candidates = materialize_import(state, previous, mutable)
            errors = record_errors(record)
            if errors:
                raise HTTPException(422, errors)
            return {"record": record, "candidates": candidates}

    @app.post("/api/records/{revision_id}/complete-import")
    async def complete_import(revision_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Confirm a reviewed import, populate candidates, and save a completed record."""
        async with lock:
            state = await asyncio.to_thread(read_state)
            previous = state["records"].get(str(revision_id))
            if previous is None:
                raise HTTPException(404, "Start the revision first")
            if payload.get("version") != previous["version"]:
                raise HTTPException(409, "Newer version exists; reload before editing")
            mutable = payload.get("payload")
            if not isinstance(mutable, dict):
                raise HTTPException(422, "Import payload must be an object")
            errors = [error.message for error in import_validator.iter_errors(mutable)]
            if errors:
                raise HTTPException(422, errors)
            record, registry, _ = materialize_import(state, previous, mutable)
            errors = record_errors(record)
            if errors:
                raise HTTPException(422, errors)
            item = {"record": record, "status": "completed", "version": previous["version"] + 1}
            state["records"][str(revision_id)] = item
            state["registry"] = registry
            await asyncio.to_thread(save_state, state)
            return item

    @app.post("/api/registry")
    async def registry(entity: dict[str, Any]) -> dict[str, Any]:
        async with lock:
            state = await asyncio.to_thread(read_state)
            if (
                not isinstance(entity.get("canonical_name"), str)
                or not entity["canonical_name"].strip()
            ):
                raise HTTPException(422, "Canonical name is required")
            if (
                entity.get("entity_type")
                not in schema["$defs"]["entity"]["properties"]["entity_type"]["enum"]
            ):
                raise HTTPException(422, "Invalid entity type")
            entry = {
                "id": next_registry_id(state["registry"]),
                "canonical_name": entity["canonical_name"].strip(),
                "aliases": [entity.get("surface_form", entity["canonical_name"])],
                "entity_type": entity["entity_type"],
                "status": "candidate",
            }
            state["registry"].append(entry)
            await asyncio.to_thread(save_state, state)
            return entry

    static = Path(os.environ.get("ANNOTATION_STATIC", str(ROOT / "annotation-ui/web/dist")))
    if static.exists():
        app.mount("/", StaticFiles(directory=static, html=True), name="ui")
    return app


app = create_app()
