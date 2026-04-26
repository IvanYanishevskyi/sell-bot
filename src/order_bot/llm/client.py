from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


@dataclass
class LLMClientConfig:
    provider: str
    api_key: str | None
    model: str
    base_url: str | None = None
    openrouter_site_url: str | None = None
    openrouter_app_name: str | None = None


class JSONLLMClient:
    def __init__(self, config: LLMClientConfig) -> None:
        self.model = config.model
        self.provider = config.provider
        self._client = None

        if OpenAI is None or not config.api_key:
            return

        base_url = config.base_url
        default_headers: dict[str, str] = {}

        if config.provider == "openrouter":
            base_url = base_url or "https://openrouter.ai/api/v1"
            if config.openrouter_site_url:
                default_headers["HTTP-Referer"] = config.openrouter_site_url
            if config.openrouter_app_name:
                default_headers["X-Title"] = config.openrouter_app_name

        client_kwargs: dict[str, Any] = {"api_key": config.api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        if default_headers:
            client_kwargs["default_headers"] = default_headers

        self._client = OpenAI(**client_kwargs)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def parse_json(self, system_prompt: str, raw_text: str) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("LLM client is not configured")

        completion = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )

        content = completion.choices[0].message.content or "{}"
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError("Expected JSON object from LLM")
        return payload
