"""LiteLLM client for the three schema-constrained inference-v3 requests."""

import json
import time
from typing import Any, cast

from monitoring_common.contracts import PassName, load_extraction_schema, load_inference_schema
from openai import AsyncOpenAI

from telegram_monitor_ai_worker.models import ModelOutputError, ModelResponse
from telegram_monitor_ai_worker.prompt import (
    LEGACY_SYSTEM_PROMPT,
    SYSTEM_PROMPTS,
    pass_message,
    repair_message,
)


class LiteLlmInferenceClient:
    """Call the internal OpenAI-compatible LiteLLM endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        entities_max_output_tokens: int = 1024,
        claims_max_output_tokens: int = 4096,
        classification_max_output_tokens: int = 1024,
    ) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout_seconds)
        self._model = model
        self._entities_max_output_tokens = entities_max_output_tokens
        self._claims_max_output_tokens = claims_max_output_tokens
        self._classification_max_output_tokens = classification_max_output_tokens

    async def infer(self, pass_name: PassName, request: dict[str, Any]) -> ModelResponse:
        """Generate one primary pass response as raw JSON text."""
        return await self._request(
            pass_name,
            [
                {"role": "system", "content": SYSTEM_PROMPTS[pass_name]},
                {"role": "user", "content": pass_message(pass_name, request)},
            ],
            self._max_tokens(pass_name, request),
        )

    async def repair(
        self,
        pass_name: PassName,
        original_raw: str,
        errors: list[dict[str, str]],
    ) -> ModelResponse:
        """Generate the one allowed structural repair response."""
        return await self._request(
            pass_name,
            [
                {"role": "system", "content": SYSTEM_PROMPTS[pass_name]},
                {
                    "role": "user",
                    "content": repair_message(
                        pass_name, original_raw, errors, load_inference_schema(pass_name)
                    ),
                },
            ],
            self._max_tokens(pass_name, {}),
        )

    def _max_tokens(self, pass_name: PassName, request: dict[str, Any]) -> int:
        """Return the output budget appropriate for one focused inference pass."""
        if pass_name == "entities":
            return self._entities_max_output_tokens
        if pass_name == "claims":
            return self._claims_max_output_tokens
        items = request.get("items", [])
        item_count = len(items) if isinstance(items, list) else 0
        return min(128 + item_count * 128, self._classification_max_output_tokens)

    async def _request(
        self, pass_name: PassName, messages: list[dict[str, str]], max_tokens: int
    ) -> ModelResponse:
        started = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=cast(Any, messages),
            response_format=cast(
                Any,
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": f"telegram_monitor_{pass_name}",
                        "strict": True,
                        "schema": load_inference_schema(pass_name),
                    },
                },
            ),
            temperature=0,
            max_tokens=max_tokens,
        )
        duration_ms = round((time.monotonic() - started) * 1000)
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise ModelOutputError("model generation did not contain JSON content")
        finish_reason = (
            getattr(response.choices[0], "finish_reason", None) if response.choices else None
        )
        usage = getattr(response, "usage", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        return ModelResponse(content, duration_ms, finish_reason, completion_tokens)

    async def close(self) -> None:
        """Close the underlying asynchronous HTTP client."""
        await self._client.close()


class LiteLlmExtractionClient:
    """Frozen v1 client retained only for the historical comparison runner."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout_seconds: int) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout_seconds)
        self._model = model

    async def extract(self, post_text: str) -> dict[str, Any]:
        """Request the legacy v1 response used by mamay_golden_v0."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": LEGACY_SYSTEM_PROMPT},
                {"role": "user", "content": f"POST TEXT:\n\n{post_text}"},
            ],
            response_format=cast(
                Any,
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "post_analysis_extraction",
                        "strict": True,
                        "schema": load_extraction_schema(),
                    },
                },
            ),
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
        """Close the legacy HTTP client."""
        await self._client.close()
