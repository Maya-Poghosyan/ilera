"""Embeddings with three tiers, in priority order:

1. OpenAI (if OPENAI_API_KEY set) — strongest, hosted.
2. fastembed (local ONNX model, no API key) — good semantic quality, default.
3. Hashed bag-of-words — last-resort fallback if fastembed can't load.
"""

import hashlib
import re

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

        _fastembed_model = TextEmbedding(model_name=get_settings().fastembed_model)
    return _fastembed_model


def provider() -> str:
    s = get_settings()
    if s.openai_api_key:
        return "openai"
    try:
        _get_fastembed()
        return "fastembed"
    except Exception:
        return "hash"


def embed(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    if s.openai_api_key:
        from openai import OpenAI

        client = OpenAI(api_key=s.openai_api_key)
        resp = client.embeddings.create(model=s.embedding_model, input=texts)
        return [d.embedding for d in resp.data]
    try:
        model = _get_fastembed()
        return [v.tolist() for v in model.embed(texts)]
    except Exception:
        return [_fallback_embed(t) for t in texts]


def embed_one(text: str) -> list[float]:
    return embed([text])[0]


def dim() -> int:
    p = provider()
    if p == "openai":
        return 1536
    if p == "fastembed":
        return 384  # BAAI/bge-small-en-v1.5
    return FALLBACK_DIM
