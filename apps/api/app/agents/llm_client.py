"""Provider-agnostic LLM client abstraction.

All agent nodes (Planner, Coder, Reviewer …) call ``get_llm_client()`` to
obtain an ``LLMClient`` instance and then call ``generate_structured`` to
get a Pydantic-validated response.  **No agent node imports google-genai
directly** — they only import from this module.  That means swapping to a
different provider later is a single change here, touching zero node logic.

Currently implemented providers
---------------------------------
- ``"gemini"`` — Google Gemini via the ``google-genai`` SDK (v2+).
  Structured output is requested with ``response_mime_type="application/json"``
  and ``response_schema=<PydanticClass>``, so the model's output is
  schema-validated by the SDK before we ever parse it.

Adding a new provider
---------------------
1. Implement a class that inherits ``LLMClient`` and overrides
   ``generate_structured``.
2. Add a branch to ``get_llm_client`` mapping your provider string to the
   new class.
3. No agent node files need to change.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypeVar

from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_RETRIES = 1  # one retry after the initial attempt, matching Voyage pattern


# ---------------------------------------------------------------------------
# Typed exception
# ---------------------------------------------------------------------------


class LLMError(RuntimeError):
    """Raised when the LLM API fails after all retries, or for config errors."""


# ---------------------------------------------------------------------------
# Response wrapper
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    """Structured output from an LLM call, bundled with usage telemetry.

    Attributes
    ----------
    result
        Pydantic model instance validated against the requested schema.
    input_tokens
        Number of prompt tokens consumed (0 if the provider doesn't report it).
    output_tokens
        Number of completion tokens generated.
    latency_ms
        Wall-clock time from request send to response received, in milliseconds.
    """

    result: BaseModel
    input_tokens: int
    output_tokens: int
    latency_ms: int


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class LLMClient(ABC):
    """Minimal interface every provider implementation must satisfy."""

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        schema: type[T],
    ) -> LLMResponse:
        """Call the LLM and return a schema-validated result with usage info.

        Args:
            prompt: The complete prompt string to send.
            schema: A Pydantic ``BaseModel`` subclass; the LLM is instructed
                to return JSON conforming to this schema.

        Returns:
            ``LLMResponse`` whose ``result`` is an instance of *schema*.

        Raises:
            LLMError: If the API fails after all retries or the response
                cannot be parsed into *schema*.
        """


# ---------------------------------------------------------------------------
# Gemini implementation
# ---------------------------------------------------------------------------


class GeminiClient(LLMClient):
    """LLM client backed by Google Gemini via the ``google-genai`` SDK.

    Uses ``response_mime_type="application/json"`` + ``response_schema`` to
    request structured output, then validates the parsed result against
    the caller-supplied Pydantic model.

    Retries once (with 2-second backoff) on any API error before raising
    ``LLMError`` — the same pattern used by the Voyage embedding client.
    """

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def generate_structured(
        self,
        prompt: str,
        schema: type[T],
    ) -> LLMResponse:
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                t0 = time.perf_counter()
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                    ),
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)

                # Extract parsed result — SDK may populate response.parsed when
                # response_schema is a Pydantic class; fall back to text parse.
                parsed_raw = response.parsed
                if isinstance(parsed_raw, schema):
                    result: T = parsed_raw
                elif isinstance(parsed_raw, dict):
                    result = schema.model_validate(parsed_raw)
                else:
                    text = response.text
                    if text is None:
                        raise LLMError("LLM returned no text and no parsed result")
                    result = schema.model_validate_json(text)

                usage = response.usage_metadata
                return LLMResponse(
                    result=result,
                    input_tokens=int(usage.prompt_token_count or 0) if usage else 0,
                    output_tokens=(
                        int(usage.candidates_token_count or 0) if usage else 0
                    ),
                    latency_ms=latency_ms,
                )

            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = 2.0 ** (attempt + 1)
                    logger.warning(
                        "Gemini API error — retrying",
                        extra={
                            "attempt": attempt + 1,
                            "wait_s": wait,
                            "model": self._model,
                            "error": str(exc),
                        },
                    )
                    await asyncio.sleep(wait)

        raise LLMError(
            f"Gemini API failed after {_MAX_RETRIES + 1} attempt(s)"
        ) from last_exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_llm_client() -> LLMClient:
    """Return the LLM client for the configured provider.

    Reads ``settings.LLM_PROVIDER``; raises ``LLMError`` for any value that
    doesn't have an implementation, rather than silently defaulting — this
    makes misconfiguration loud and obvious at runtime.
    """
    provider = settings.LLM_PROVIDER.lower()
    if provider == "gemini":
        return GeminiClient(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
        )
    raise LLMError(
        f"Unknown LLM provider: {settings.LLM_PROVIDER!r}. "
        "Implement a new LLMClient subclass and add it to get_llm_client()."
    )
