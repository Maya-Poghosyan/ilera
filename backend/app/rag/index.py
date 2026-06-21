"""RAG index over official program documentation.

Uses Redis (via raw redis-py vector ops kept simple) when configured, otherwise an
in-memory cosine index so retrieval works without infrastructure. For production-grade
indexing, replace the in-memory path with RedisVL's SearchIndex + HNSW schema.
"""

import glob
import os
from dataclasses import dataclass, field

from ..config import get_settings
from .embeddings import embed, embed_one

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "program_docs")
CHUNK_CHARS = 800


@dataclass
class Chunk:
    id: str
    program: str
    text: str
    source: str
    vector: list[float] = field(default_factory=list)


@dataclass
class Retrieved:
    text: str
    program: str
    source: str
    score: float


class RagIndex:
    """Minimal vector index. Swap for RedisVL SearchIndex when scaling up."""

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []

    @property
    def size(self) -> int:
        return len(self._chunks)

    def _load_docs(self) -> list[Chunk]:
        chunks: list[Chunk] = []
        for path in glob.glob(os.path.join(DATA_DIR, "*.txt")):
            program = os.path.splitext(os.path.basename(path))[0]
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for i in range(0, len(text), CHUNK_CHARS):
                piece = text[i : i + CHUNK_CHARS].strip()
                if piece:
                    chunks.append(
                        Chunk(
                            id=f"{program}:{i}",
                            program=program,
                            text=piece,
                            source=os.path.basename(path),
                        )
                    )
        return chunks

    def build(self) -> int:
        chunks = self._load_docs()
        if chunks:
            vectors = embed([c.text for c in chunks])
            for c, v in zip(chunks, vectors):
                c.vector = v
        self._chunks = chunks
        return len(chunks)

    def search(self, query: str, k: int = 4, program: str | None = None) -> list[Retrieved]:
        if not self._chunks:
            return []
        qv = embed_one(query)
        results: list[Retrieved] = []
        for c in self._chunks:
            if program and c.program != program:
                continue
            score = _cosine(qv, c.vector)
            results.append(Retrieved(text=c.text, program=c.program, source=c.source, score=score))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


_index: RagIndex | None = None


def get_index() -> RagIndex:
    global _index
    if _index is None:
        _index = RagIndex()
        _index.build()
    return _index
