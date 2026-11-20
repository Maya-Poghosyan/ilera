"""Embeddings through the hosted OpenAI-compatible endpoint (Azure OpenAI in production)."""

import logging
import time
from collections.abc import Iterable, Iterator

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DIM = 1536  # text-embedding-3-small
_openai_client = None


def model_id() -> str:
    """The model whose vectors are in the index. Part of a document's fingerprint, so
    switching models re-embeds the corpus rather than mixing incomparable vectors."""
    return get_settings().embedding_model


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        s = get_settings()
        _openai_client = OpenAI(
            api_key=s.openai_api_key,
            base_url=s.openai_base_url,
            max_retries=s.embedding_max_retries,
            timeout=s.embedding_timeout_seconds,
        )
    return _openai_client


def _embed_batch(texts: list[str]) -> list[list[float]]:
    """One embeddings request, retried on transient failures.

    An ingest is thousands of sequential requests, so a single 429/503 must not abort it;
    the client's own retries cover most of it and this outer loop covers the rest.
    """
    s = get_settings()
    delay = 5.0
    for attempt in range(s.embedding_max_retries + 1):
        try:
            resp = _get_openai_client().embeddings.create(
                model=s.embedding_model, input=texts
            )
            return [d.embedding for d in resp.data]
        except Exception as exc:
            if attempt == s.embedding_max_retries:
                raise
            wait = max(delay, _retry_after(exc))
            logger.warning(
                "Embedding request failed (attempt %d), retrying in %.0fs: %s",
                attempt + 1, wait, exc,
            )
            time.sleep(wait)
            delay = min(delay * 2, 60.0)
    raise AssertionError("unreachable")


def _retry_after(exc: Exception) -> float:
    """Seconds the provider asked us to wait. A throttled tier answers 429 with Retry-After
    (often 60s), which is far longer than a naive backoff would pick."""
    response = getattr(exc, "response", None)
    header = getattr(response, "headers", {}).get("retry-after") if response else None
    try:
        return float(header) if header else 0.0
    except ValueError:
        return 0.0


def batch_size() -> int:
    """Texts per embedding request; the limit is round trips, not memory."""
    return max(1, get_settings().embedding_api_batch_size)


def embed_iter(texts: Iterable[str]) -> Iterator[list[float]]:
    """Embed lazily in batches, yielding one vector at a time, so callers can write vectors
    out incrementally instead of holding the whole corpus."""
    size = batch_size()
    batch: list[str] = []
    for text in texts:
        batch.append(text)
        if len(batch) >= size:
            yield from _embed_batch(batch)
            batch = []
    if batch:
        yield from _embed_batch(batch)


def embed(texts: list[str]) -> list[list[float]]:
    return list(embed_iter(texts))


def embed_one(text: str) -> list[float]:
    return _embed_batch([text])[0]
