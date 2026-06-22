"""Voyage AI embedding utilities.

Batches texts to stay within Voyage's per-request limit and retries on
transient failures with exponential back-off.  Rate-limit (429) responses
are caught specifically and given longer back-offs since the free tier
allows only ~3 requests per minute.
"""

import asyncio
import logging

import voyageai
from voyageai.error import RateLimitError as VoyageRateLimitError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Voyage AI accepts up to 128 texts or 120 000 tokens per request.
_BATCH_SIZE = 128

# 4 retries → 5 total attempts.  Backoff starts at 30 s and doubles each
# time: 30 s → 60 s → 120 s → 240 s.  The free tier allows ~3 RPM, so the
# first retry at 30 s is enough to clear a transient quota window.
_MAX_RETRIES = 4
_BACKOFF_BASE = 30.0  # seconds — doubles on each retry

# For repos that produce more than _LARGE_REPO_THRESHOLD chunks, a 20-second
# sleep is inserted between embedding batches so consecutive requests don't
# exceed the 3-RPM free-tier limit.
_INTER_BATCH_SLEEP = 20.0  # seconds
_LARGE_REPO_THRESHOLD = 500  # chunk count


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
    batch with a single Voyage API call.  For large repos (> ``_LARGE_REPO_THRESHOLD``
    chunks) a mandatory ``_INTER_BATCH_SLEEP``-second sleep is inserted between
    batches to avoid breaching the free-tier 3-RPM limit.

    Retries up to ``_MAX_RETRIES`` times with exponential back-off starting at
    ``_BACKOFF_BASE`` seconds.  Rate-limit errors (HTTP 429) are caught
    separately and given the same back-off schedule.

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
    needs_inter_batch_sleep = len(texts) > _LARGE_REPO_THRESHOLD

    for i in range(0, len(texts), _BATCH_SIZE):
        if needs_inter_batch_sleep and i > 0:
            logger.info(
                "Large repo (%d chunks) — sleeping %.0fs between batches "
                "to stay under Voyage free-tier 3 RPM limit",
                len(texts),
                _INTER_BATCH_SLEEP,
            )
            await asyncio.sleep(_INTER_BATCH_SLEEP)

        batch = texts[i : i + _BATCH_SIZE]
        embeddings = await _embed_batch(client, batch, input_type)
        all_embeddings.extend(embeddings)

    return all_embeddings


async def _embed_batch(
    client: voyageai.AsyncClient,  # type: ignore[attr-defined]
    texts: list[str],
    input_type: str,
) -> list[list[float]]:
    """Embed one batch, retrying on transient failures with exponential back-off.

    Back-off schedule (``_BACKOFF_BASE = 30``):
      attempt 1 failed → wait 30 s
      attempt 2 failed → wait 60 s
      attempt 3 failed → wait 120 s
      attempt 4 failed → wait 240 s
    """
    last_exc: Exception | None = None
    last_was_rate_limit = False

    for attempt in range(_MAX_RETRIES + 1):
        try:
            result = await client.embed(
                texts,
                model=settings.VOYAGE_MODEL,
                input_type=input_type,
            )
            return result.embeddings  # type: ignore[no-any-return]
        except VoyageRateLimitError as exc:
            last_exc = exc
            last_was_rate_limit = True
            if attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE * (2.0**attempt)  # 30, 60, 120, 240
                logger.warning(
                    "Voyage API rate limited (429) — retrying in %.0fs "
                    "(attempt %d/%d)",
                    wait,
                    attempt + 1,
                    _MAX_RETRIES,
                    extra={"attempt": attempt + 1, "wait_s": wait, "error": str(exc)},
                )
                await asyncio.sleep(wait)
        except Exception as exc:
            last_exc = exc
            last_was_rate_limit = False
            if attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE * (2.0**attempt)
                logger.warning(
                    "Voyage API error — retrying in %.0fs (attempt %d/%d)",
                    wait,
                    attempt + 1,
                    _MAX_RETRIES,
                    extra={"attempt": attempt + 1, "wait_s": wait, "error": str(exc)},
                )
                await asyncio.sleep(wait)

    if last_was_rate_limit:
        raise EmbeddingError(
            "Voyage API rate limit exceeded. "
            "Wait 5 minutes, then delete this repo entry and re-register."
        ) from last_exc
    raise EmbeddingError(
        f"Voyage API failed after {_MAX_RETRIES + 1} attempt(s)"
    ) from last_exc
