"""Embeddings with three tiers, in priority order:

1. OpenAI (if OPENAI_API_KEY set) — strongest, hosted.
2. fastembed (local ONNX model, no API key) — good semantic quality, default.
3. Hashed bag-of-words — last-resort fallback if fastembed can't load.
"""

import hashlib
import re
from collections.abc import Iterable, Iterator

from ..config import get_settings

FALLBACK_DIM = 256
_fastembed_model = None


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


def _embed_batch(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    if _use_openai():
        from openai import OpenAI

        client = OpenAI(
            api_key=s.openai_api_key, base_url=s.openai_base_url or None
        )
        resp = client.embeddings.create(model=s.embedding_model, input=texts)
        return [d.embedding for d in resp.data]
    try:
        model = _get_fastembed()
        return [v.tolist() for v in model.embed(texts, batch_size=len(texts))]
    except Exception:
        return [_fallback_embed(t) for t in texts]


def embed_iter(texts: Iterable[str]) -> Iterator[list[float]]:
    """Embed lazily in small batches, yielding one vector at a time.

    Batch size dominates peak memory: transformer attention costs
    O(batch x heads x seq^2), so embedding a whole corpus in one call at fastembed's
    default batch of 256 allocates several GB (measured ~8.8 GB peak RSS for this
    corpus) and OOMs a small container, while a batch of `embedding_batch_size`
    keeps the build flat. Callers should also consume this lazily so the vectors are
    written out incrementally instead of all being held at once.
    """
    size = max(1, get_settings().embedding_batch_size)
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
