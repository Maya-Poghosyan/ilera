"""Embeddings with a deterministic local fallback.

When an OpenAI key is set we use the real embedding model. Otherwise we fall back to a
hashed bag-of-words vector so RAG works end-to-end during development without keys.
The fallback is NOT semantically strong; set OPENAI_API_KEY for real retrieval.
"""

import hashlib
import re

from ..config import get_settings

FALLBACK_DIM = 256


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _fallback_embed(text: str) -> list[float]:
    vec = [0.0] * FALLBACK_DIM
    for tok in _tokenize(text):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % FALLBACK_DIM] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def embed(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    if settings.openai_api_key:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.embeddings.create(model=settings.embedding_model, input=texts)
        return [d.embedding for d in resp.data]
    return [_fallback_embed(t) for t in texts]


def embed_one(text: str) -> list[float]:
    return embed([text])[0]


def dim() -> int:
    settings = get_settings()
    if settings.openai_api_key:
        # text-embedding-3-small default dimensionality
        return 1536
    return FALLBACK_DIM
