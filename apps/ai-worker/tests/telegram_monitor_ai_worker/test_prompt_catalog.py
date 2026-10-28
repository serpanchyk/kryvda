import json
from pathlib import Path

from telegram_monitor_ai_worker.prompt import SYSTEM_PROMPTS
from telegram_monitor_ai_worker.prompt_catalog import (
    CATALOG_PATH,
    main,
    prompt_catalog,
    render_catalog,
)


def test_catalog_lists_every_pass_in_pipeline_order() -> None:
    catalog = prompt_catalog()

    assert [item["name"] for item in catalog["passes"]] == [
        "candidates",
        "entities",
        "claims",
        "targets",
        "classification",
        "affiliations",
    ]
    assert all(item["system_prompt"] == SYSTEM_PROMPTS[item["name"]] for item in catalog["passes"])
    assert all(item["schema"]["type"] == "object" for item in catalog["passes"])
    assert catalog["repair_instruction"].startswith("Виправ лише структуру")


def test_committed_catalog_matches_the_running_prompts() -> None:
    """Regenerate with `python -m telegram_monitor_ai_worker.prompt_catalog` after edits."""
    assert CATALOG_PATH.read_text(encoding="utf-8") == render_catalog()


def test_main_writes_the_catalog(tmp_path: Path) -> None:
    target = tmp_path / "catalog.json"

    main([str(target)])

    assert json.loads(target.read_text(encoding="utf-8")) == prompt_catalog()
