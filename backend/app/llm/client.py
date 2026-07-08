"""LiteLLM client wrapper.

Keeps the model fully swappable (Groq Llama today, anything tomorrow). When no
API key is configured, `enabled` is False and callers fall back to the
deterministic rule-based paths — the platform still runs end-to-end, and the
verification kernel still owns the truth.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import structlog

from app.config import settings

log = structlog.get_logger(__name__)


class LLMClient:
    def __init__(self) -> None:
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.enabled = settings.llm_enabled

    def complete(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        if not self.enabled:
            raise RuntimeError(
                "LLM not configured. Please set the appropriate API key (GROQ_API_KEY or OPENROTER_API_KEY) in your environment."
            )
        import litellm

        # Per-provider auth:
        auth: dict[str, Any] = {}
        if settings.is_openrouter:
            auth["api_key"] = settings.openrouter_api_key
        else:
            auth["api_key"] = settings.groq_api_key

        # Some providers/models don't support every param (e.g. response_format
        # JSON mode); let LiteLLM drop unsupported ones instead of erroring.
        litellm.drop_params = True

        resp = litellm.completion(
            model=self.model,
            messages=messages,
            temperature=kwargs.pop("temperature", self.temperature),
            **auth,
            **kwargs,
        )
        return resp["choices"][0]["message"]["content"]

    def complete_json(self, system: str, user: str, **kwargs: Any) -> Any:
        """Ask for strict JSON and parse it. Raises on failure — there is no
        rule-based fallback. The caller must surface the error, not fake data.

        The one recovery attempt here is a JSON re-parse (salvaging a valid JSON
        object from a chatty response); a hard model/network failure propagates.
        """
        if not self.enabled:
            raise RuntimeError("LLM not configured. Agent layer requires a configured LLM provider.")
        content = self.complete(
            [
                {"role": "system", "content": system + "\nRespond with valid JSON only."},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            **kwargs,
        )
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            salvaged = _extract_json(content)
            if salvaged is not None:
                return salvaged
            log.error("llm_json_unparseable", preview=content[:200])
            raise


def _extract_json(text: str) -> Any:
    """Salvage the first balanced JSON object/array from a chatty response."""
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == open_ch:
                depth += 1
            elif text[i] == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    return None


@lru_cache
def get_llm() -> LLMClient:
    return LLMClient()
