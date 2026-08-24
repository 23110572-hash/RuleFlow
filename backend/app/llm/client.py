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


def _api_key_for(model: str) -> str:
    return settings.openrouter_api_key if model.startswith("openrouter/") else settings.groq_api_key


class LLMClient:
    def __init__(self) -> None:
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.enabled = settings.llm_enabled

    def _call(
        self, model: str, messages: list[dict[str, str]], **kwargs: Any
    ) -> tuple[str, str | None]:
        """Returns (content, finish_reason).

        ``finish_reason`` is load-bearing: "length" means the model was cut off
        at ``max_tokens`` mid-sentence. Without it, a truncated reply is
        indistinguishable from a broken provider — the JSON simply fails to
        parse and the caller has no idea the model had more to say.
        """
        import litellm

        # Some providers/models don't support every param (e.g. response_format
        # JSON mode); let LiteLLM drop unsupported ones instead of erroring.
        litellm.drop_params = True

        resp = litellm.completion(
            model=model,
            messages=messages,
            temperature=kwargs.pop("temperature", self.temperature),
            # max_tokens is NOT optional. OpenRouter pre-authorises the model's
            # full output ceiling when it is omitted and returns HTTP 402 even
            # with credit remaining. See settings.llm_max_tokens.
            max_tokens=kwargs.pop("max_tokens", settings.llm_max_tokens),
            timeout=kwargs.pop("timeout", settings.llm_timeout),
            num_retries=kwargs.pop("num_retries", settings.llm_num_retries),
            api_key=_api_key_for(model),
            **kwargs,
        )
        choice = resp["choices"][0]
        content = choice["message"]["content"] or ""
        try:
            finish = choice["finish_reason"]
        except Exception:  # provider/SDK shape differences must not be fatal
            finish = getattr(choice, "finish_reason", None)
        return content, finish

    def complete_with_reason(
        self, messages: list[dict[str, str]], **kwargs: Any
    ) -> tuple[str, str | None]:
        """:meth:`complete`, but also reporting why generation stopped."""
        if not self.enabled:
            raise RuntimeError(
                "LLM not configured. Please set the appropriate API key "
                "(GROQ_API_KEY or OPENROUTER_API_KEY) in your environment."
            )
        try:
            return self._call(self.model, messages, **kwargs)
        except Exception as primary_exc:
            if not settings.llm_fallback_enabled:
                raise
            log.warning(
                "llm_primary_failed_trying_fallback",
                primary=self.model,
                fallback=settings.llm_fallback_model,
                error=str(primary_exc)[:300],
            )
            try:
                return self._call(settings.llm_fallback_model, messages, **kwargs)
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"Both LLM providers failed. {self.model}: {primary_exc}. "
                    f"{settings.llm_fallback_model}: {fallback_exc}"
                ) from fallback_exc

    def complete(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return self.complete_with_reason(messages, **kwargs)[0]

    def complete_json(self, system: str, user: str, **kwargs: Any) -> Any:
        """Ask for strict JSON and parse it. Raises on failure — there is no
        rule-based fallback. The caller must surface the error, not fake data.

        Two recovery attempts happen here:

        1. If the model was cut off at ``max_tokens`` (``finish_reason ==
           "length"``), the reply is truncated mid-JSON and can never parse. Ask
           again once with a larger ceiling instead of reporting the whole call
           as failed. A dense clause that yields a dozen obligations would
           otherwise be written off entirely.
        2. A JSON re-parse, salvaging a valid object from a chatty response.

        A hard model/network failure propagates.
        """
        if not self.enabled:
            raise RuntimeError("LLM not configured. Agent layer requires a configured LLM provider.")
        messages = [
            {"role": "system", "content": system + "\nRespond with valid JSON only."},
            {"role": "user", "content": user},
        ]
        cap = kwargs.pop("max_tokens", settings.llm_max_tokens)
        content, finish = self.complete_with_reason(
            messages, response_format={"type": "json_object"}, max_tokens=cap, **kwargs
        )

        if finish == "length":
            bigger = min(settings.llm_max_tokens_ceiling, cap * 2)
            if bigger > cap:
                log.warning(
                    "llm_response_truncated_retrying", cap=cap, retry_cap=bigger
                )
                content, finish = self.complete_with_reason(
                    messages,
                    response_format={"type": "json_object"},
                    max_tokens=bigger,
                    **kwargs,
                )
            if finish == "length":
                # Still cut off at the ceiling. Say so plainly rather than
                # letting it surface as an unexplained parse error.
                log.error("llm_response_truncated_at_ceiling", cap=bigger)

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            salvaged = _extract_json(content)
            if salvaged is not None:
                return salvaged
            log.error(
                "llm_json_unparseable", finish_reason=finish, preview=content[:200]
            )
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
