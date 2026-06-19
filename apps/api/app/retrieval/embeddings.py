"""Voyage AI embedding utilities.

Batches texts to stay within Voyage's per-request limit and retries once
with exponential back-off on transient failures before giving up.
"""

import asyncio
import logging

import voyageai

from app.core.config import settings

logger = logging.getLogger(__name__)

# Voyage AI accepts up to 128 texts or 120 000 tokens per request,
# whichever is hit first.  128 is a safe upper bound for code chunks.
_BATCH_SIZE = 128
_MAX_RETRIES = 1


# ---------------------------------------------------------------------------
# Typed exception
# ---------------------------------------------------------------------------


class EmbeddingError(RuntimeError):
    """Raised when the Voyage API fails after all retries."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def embed_texts(
    texts: list[str],
    input_type: str = "document",
) -> list[list[float]]:
    """Return one embedding vector per text in *texts*.

    Splits *texts* into batches of at most ``_BATCH_SIZE`` and embeds each
    batch with a single Voyage API call.  Retries up to ``_MAX_RETRIES``
    times with 2-second back-off on any transient error.

    Args:
        texts: Texts to embed.
        input_type: ``"document"`` for indexed chunks; ``"query"`` for search
            queries.  Voyage AI uses asymmetric embeddings for retrieval.

    Raises:
        EmbeddingError: If the API fails for a batch after all retries.
    """
    if not texts:
        return []

    client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)  # type: ignore[attr-defined]
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        embeddings = await _embed_batch(client, batch, input_type)
        all_embeddings.extend(embeddings)

    return all_embeddings


async def _embed_batch(
    client: voyageai.AsyncClient,  # type: ignore[attr-defined]
    texts: list[str],
    input_type: str,
) -> list[list[float]]:
    """Embed one batch, retrying on transient failures with back-off."""
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            result = await client.embed(
                texts,
                model=settings.VOYAGE_MODEL,
                input_type=input_type,
            )
            return result.embeddings  # type: ignore[no-any-return]
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                wait = 2.0 ** (attempt + 1)  # 2s, 4s, …
                logger.warning(
                    "Voyage API error — retrying",
                    extra={
                        "attempt": attempt + 1,
                        "wait_s": wait,
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(wait)

    raise EmbeddingError(
        f"Voyage API failed after {_MAX_RETRIES + 1} attempt(s)"
    ) from last_exc
