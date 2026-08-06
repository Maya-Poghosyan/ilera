"""Embeddings with three tiers, in priority order:

1. OpenAI (if OPENAI_API_KEY set) — strongest, hosted, and keeps no model in this process.
2. fastembed (local ONNX model, no API key) — good semantic quality, but the model and its
   activation buffers live in this process's memory.
3. Hashed bag-of-words — last-resort fallback if fastembed can't load.
"""

import hashlib
import logging
import re
import time
from collections.abc import Iterable, Iterator

from ..config import get_settings

logger = logging.getLogger(__name__)

FALLBACK_DIM = 256
_fastembed_model = None
_openai_client = None


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _fallback_embed(text: str) -> list[float]:
    vec = [0.0] * FALLBACK_DIM
    for tok in _tokenize(text):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % FALLBACK_DIM] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _get_fastembed():
    global _fastembed_model
    if _fastembed_model is None:
        from fastembed import TextEmbedding

        s = get_settings()
        _fastembed_model = TextEmbedding(
            model_name=s.fastembed_model, threads=max(1, s.embedding_threads)
        )
    return _fastembed_model


def _use_openai() -> bool:
    s = get_settings()
    mode = (s.embedding_provider or "auto").lower()
    if mode == "openai":
        return True
    if mode == "fastembed":
        return False
    return bool(s.openai_api_key)  # "auto"


def provider() -> str:
    if _use_openai():
        return "openai"
    try:
        _get_fastembed()
        return "fastembed"
    except Exception:
        return "hash"


def model_id() -> str:
    """The model whose vectors are in the index. Part of a document's fingerprint, so
    switching models re-embeds the corpus rather than mixing incomparable vectors."""
    s = get_settings()
    p = provider()
    if p == "openai":
        return s.embedding_model
    if p == "fastembed":
        return s.fastembed_model
    return "hash"


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        s = get_settings()
        _openai_client = OpenAI(
            api_key=s.openai_api_key,
            base_url=s.openai_base_url or None,
            max_retries=s.embedding_max_retries,
            timeout=s.embedding_timeout_seconds,
        )
    return _openai_client


def _openai_embed(texts: list[str]) -> list[list[float]]:
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


def _embed_batch(texts: list[str]) -> list[list[float]]:
    if _use_openai():
        return _openai_embed(texts)
    try:
        model = _get_fastembed()
        return [v.tolist() for v in model.embed(texts, batch_size=len(texts))]
    except Exception:
        return [_fallback_embed(t) for t in texts]


def batch_size() -> int:
    """Texts per embedding call. The two providers are limited by opposite things: the local
    model by memory (attention is O(batch x heads x seq^2), so a big batch allocates GBs),
    the hosted one by request count, where a tiny batch means thousands of round trips."""
    s = get_settings()
    size = s.embedding_api_batch_size if _use_openai() else s.embedding_batch_size
    return max(1, size)


def embed_iter(texts: Iterable[str]) -> Iterator[list[float]]:
    """Embed lazily in batches, yielding one vector at a time.

    Callers should consume this lazily so vectors are written out incrementally rather than
    all held at once. Embedding a whole corpus in a single call was what OOMed the container:
    at fastembed's default batch of 256 this corpus peaked at ~8.8 GB RSS.
    """
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


def dim() -> int:
    p = provider()
    if p == "openai":
        return 1536
    if p == "fastembed":
        return 384  # BAAI/bge-small-en-v1.5
    return FALLBACK_DIM
