"""Publish the exact prompts and response schemas of every pass for the «Як працює» page.

The frontend has no access to the worker package, so the catalog is written to a committed JSON
file; a test fails whenever a prompt, prompt version or schema changes without regenerating it.

Example:
    uv run python -m telegram_monitor_ai_worker.prompt_catalog \
        apps/frontend/src/content/method-prompts.json
"""

import json
import sys
from pathlib import Path
from typing import Any, get_args

from monitoring_common.contracts import SCHEMA_VERSIONS, PassName, load_inference_schema

from telegram_monitor_ai_worker.pipeline import PIPELINE_VERSION
from telegram_monitor_ai_worker.prompt import PROMPT_VERSIONS, SYSTEM_PROMPTS, repair_message

CATALOG_PATH = Path("apps/frontend/src/content/method-prompts.json")


def prompt_catalog() -> dict[str, Any]:
    """Return every pass in pipeline order with its system prompt, versions and schema."""
    repair = repair_message("entities", "<вихідна відповідь моделі>", [], {})
    return {
        "pipeline_version": PIPELINE_VERSION,
        "message_format": "PASS: <назва проходу>\nINPUT JSON:\n<вхідні дані проходу>",
        "repair_instruction": repair.split("\n\n", 1)[0],
        "passes": [
            {
                "name": name,
                "prompt_version": PROMPT_VERSIONS[name],
                "schema_version": SCHEMA_VERSIONS[name],
                "system_prompt": SYSTEM_PROMPTS[name],
                "schema": load_inference_schema(name),
            }
            for name in get_args(PassName)
        ],
    }


def render_catalog() -> str:
    """Serialize the catalog exactly as it is committed."""
    return json.dumps(prompt_catalog(), ensure_ascii=False, indent=2) + "\n"


def main(arguments: list[str] | None = None) -> None:
    """Write the catalog to the given path, or to the frontend content file by default."""
    values = sys.argv[1:] if arguments is None else arguments
    path = Path(values[0]) if values else CATALOG_PATH
    path.write_text(render_catalog(), encoding="utf-8")


if __name__ == "__main__":
    main()
