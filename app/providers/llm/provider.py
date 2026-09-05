"""LLMProvider protocol + Mock and OpenRouter implementations.

Business code must depend on this interface only — never on OpenRouter SDK details.
"""
import json
import re
import time
import uuid
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.observability.logging_setup import get_logger

logger = get_logger("llm")


class LLMProvider(Protocol):
    name: str

    def complete_structured(
        self, prompt_version: str, system: str, user: str, schema: type[BaseModel], temperature: float = 0.2
    ) -> tuple[BaseModel, dict]:
        """Returns (validated_output, run_meta). Retries / repairs JSON on failure."""
        ...


def _extract_json(text: str) -> str:
    """Best-effort extraction of the outermost JSON object from a model reply."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


class MockLLMProvider:
    """Deterministic offline provider for CI / development.

    It does NOT improvise content: the caller passes structured hints (e.g. lesson
    topics, question knowledge points) and the mock shapes them into the required
    schema. Real understanding arrives when LLM_PROVIDER=openrouter with a key.
    """

    name = "mock"

    def __init__(self) -> None:
        self._handlers: dict[str, Any] = {}

    def register(self, prompt_version: str, handler) -> None:
        self._handlers[prompt_version] = handler

    def complete_structured(
        self, prompt_version: str, system: str, user: str, schema: type[BaseModel], temperature: float = 0.2
    ) -> tuple[BaseModel, dict]:
        started = time.time()
        handler = self._handlers.get(prompt_version)
        if handler is None:
            raise RuntimeError(f"MockLLMProvider has no handler registered for prompt '{prompt_version}'")
        raw = handler(user)
        out = schema.model_validate(raw)
        meta = {
            "provider": self.name,
            "model": "mock-deterministic",
            "latency_ms": int((time.time() - started) * 1000),
            "input_tokens": len(user) // 4,
            "output_tokens": len(json.dumps(raw, ensure_ascii=False)) // 4,
            "status": "succeeded",
        }
        return out, meta


class OpenRouterProvider:
    """OpenAI-compatible provider via OpenRouter. Model list is configuration, never hardcoded."""

    name = "openrouter"

    def __init__(self) -> None:
        self.base_url = settings.OPENROUTER_BASE_URL.rstrip("/")
        self.api_key = settings.OPENROUTER_API_KEY
        self.default_model = settings.LLM_DEFAULT_MODEL
        self.fallbacks = [m for m in (settings.LLM_FALLBACK_MODELS or "").split(",") if m]

    def _call_model(self, model: str, system: str, user: str, temperature: float) -> str:
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": model,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def complete_structured(
        self, prompt_version: str, system: str, user: str, schema: type[BaseModel], temperature: float = 0.2
    ) -> tuple[BaseModel, dict]:
        models = ([self.default_model] if self.default_model else []) + self.fallbacks
        if not models:
            raise RuntimeError("LLM_PROVIDER=openrouter but LLM_DEFAULT_MODEL/LLM_FALLBACK_MODELS not configured")
        last_err: Exception | None = None
        for attempt in range(2):
            for model in models:
                started = time.time()
                try:
                    text = self._call_model(model, system, user, temperature)
                except Exception as exc:  # network / rate limit / 5xx -> next model
                    last_err = exc
                    logger.warning("openrouter model=%s attempt=%s failed: %s", model, attempt, exc)
                    time.sleep(min(2**attempt, 4))
                    continue
                try:
                    out = schema.model_validate_json(_extract_json(text))
                    return out, {
                        "provider": self.name,
                        "model": model,
                        "latency_ms": int((time.time() - started) * 1000),
                        "status": "succeeded",
                    }
                except ValidationError as exc:
                    last_err = exc
                    logger.warning("structured validation failed for model=%s: %s", model, exc)
            # one retry round with backoff for rate-limit style failures
        raise RuntimeError(f"All LLM models failed: {last_err}")


_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        if settings.LLM_PROVIDER == "openrouter" and settings.OPENROUTER_API_KEY:
            _provider = OpenRouterProvider()
        else:
            from app.providers.llm import mock_handlers

            mock = MockLLMProvider()
            mock.register("lesson_summary_v1", mock_handlers.lesson_summary_v1)
            mock.register("exercise_query_rewrite_v1", mock_handlers.exercise_query_rewrite_v1)
            mock.register("question_analysis_v1", mock_handlers.question_analysis_v1)
            _provider = mock
    return _provider


def new_run_id() -> str:
    return uuid.uuid4().hex
