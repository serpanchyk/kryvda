"""LiteLLM client for schema-constrained extraction requests."""

import json
from typing import Any, cast

from monitoring_common.contracts import load_extraction_schema
from openai import AsyncOpenAI

from telegram_monitor_ai_worker.models import ModelOutputError
from telegram_monitor_ai_worker.prompt import SYSTEM_PROMPT, post_message


class LiteLlmExtractionClient:
    """Call the internal OpenAI-compatible LiteLLM endpoint."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout_seconds: int) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout_seconds)
        self._model = model

    async def extract(self, post_text: str) -> dict[str, Any]:
        """Request exactly one JSON-Schema-constrained extraction object."""
        response_format: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": "post_analysis_extraction",
                "strict": True,
                "schema": load_extraction_schema(),
            },
        }
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": post_message(post_text)},
            ],
            response_format=cast(Any, response_format),
            temperature=0,
        )
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise ModelOutputError("model response did not contain JSON content")
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError as error:
            raise ModelOutputError("model response was not valid JSON") from error
        if not isinstance(decoded, dict):
            raise ModelOutputError("model response JSON must be an object")
        return cast(dict[str, Any], decoded)

    async def close(self) -> None:
        """Close the underlying asynchronous HTTP client."""
        await self._client.close()
