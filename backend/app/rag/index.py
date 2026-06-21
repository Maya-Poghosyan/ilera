"""RAG index over official program documentation.

Two backends with the same interface:
- RedisVLIndex: vectors stored in Redis, KNN via RediSearch (used when REDIS_URL is set).
- RagIndex: in-memory cosine fallback (no infrastructure needed).
"""

import glob
import json
import os
from dataclasses import dataclass, field

from ..config import get_settings
from .embeddings import dim, embed, embed_one

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "program_docs")
CHUNK_CHARS = 800
INDEX_NAME = "ilera_docs"
KEY_PREFIX = "ilera:doc"


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


def load_chunks() -> list[Chunk]:
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


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


class RagIndex:
    """In-memory vector index."""

    backend = "memory"

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []

    @property
    def size(self) -> int:
        return len(self._chunks)

    def build(self) -> int:
        chunks = load_chunks()
        if chunks:
            for c, v in zip(chunks, embed([c.text for c in chunks])):
                c.vector = v
        self._chunks = chunks
        return len(chunks)

    def search(self, query: str, k: int = 4, program: str | None = None) -> list[Retrieved]:
        if not self._chunks:
            return []
        qv = embed_one(query)
        results = [
            Retrieved(text=c.text, program=c.program, source=c.source, score=_cosine(qv, c.vector))
            for c in self._chunks
            if not program or c.program == program
        ]
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]


class RedisVLIndex:
    """Vectors stored in Redis; KNN via RediSearch (the 'Best Use of Redis' path)."""

    backend = "redis"

    def __init__(self, redis_url: str) -> None:
        from redisvl.index import SearchIndex
        from redisvl.schema import IndexSchema

        self._dim = dim()
        schema = IndexSchema.from_dict(
            {
                "index": {"name": INDEX_NAME, "prefix": KEY_PREFIX, "storage_type": "hash"},
                "fields": [
                    {"name": "program", "type": "tag"},
                    {"name": "source", "type": "text"},
                    {"name": "text", "type": "text"},
                    {
                        "name": "vector",
                        "type": "vector",
                        "attrs": {
                            "dims": self._dim,
                            "distance_metric": "cosine",
                            "algorithm": "hnsw",
                            "datatype": "float32",
                        },
                    },
                ],
            }
        )
        self._index = SearchIndex(schema, redis_url=redis_url)
        self._size = 0

    @property
    def size(self) -> int:
        return self._size

    def build(self) -> int:
        from redisvl.redis.utils import array_to_buffer

        chunks = load_chunks()
        self._index.create(overwrite=True, drop=True)
        if chunks:
            vectors = embed([c.text for c in chunks])
            data = [
                {
                    "id": c.id,
                    "program": c.program,
                    "source": c.source,
                    "text": c.text,
                    "vector": array_to_buffer(v, dtype="float32"),
                }
                for c, v in zip(chunks, vectors)
            ]
            self._index.load(data, id_field="id")
        self._size = len(chunks)
        return self._size

    def search(self, query: str, k: int = 4, program: str | None = None) -> list[Retrieved]:
        from redisvl.query import VectorQuery
        from redisvl.query.filter import Tag

        qv = embed_one(query)
        vq = VectorQuery(
            vector=qv,
            vector_field_name="vector",
            return_fields=["program", "source", "text"],
            num_results=k,
            dtype="float32",
        )
        if program:
            vq.set_filter(Tag("program") == program)
        rows = self._index.query(vq)
        out: list[Retrieved] = []
        for r in rows:
            # redisvl returns cosine distance; convert to similarity.
            dist = float(r.get("vector_distance", 0.0))
            out.append(
                Retrieved(
                    text=r.get("text", ""),
                    program=r.get("program", ""),
                    source=r.get("source", ""),
                    score=1.0 - dist,
                )
            )
        return out


class RedisKNNIndex:
    """Vectors + metadata stored in Redis hashes; cosine ranking in Python.

    Works on any Redis (no Search module required). Used when REDIS_URL is set but the
    RediSearch/vector module is unavailable (e.g. a plain Redis Cloud Essentials DB).
    """

    backend = "redis-knn"

    def __init__(self, redis_url: str) -> None:
        import redis

        self._r = redis.from_url(redis_url, decode_responses=True, socket_timeout=8)
        self._ids_key = f"{KEY_PREFIX}:ids"
        self._size = 0

    @property
    def size(self) -> int:
        return self._size

    def build(self) -> int:
        chunks = load_chunks()
        old = self._r.smembers(self._ids_key)
        pipe = self._r.pipeline()
        for cid in old:
            pipe.delete(f"{KEY_PREFIX}:{cid}")
        pipe.delete(self._ids_key)
        if chunks:
            vectors = embed([c.text for c in chunks])
            for c, v in zip(chunks, vectors):
                pipe.hset(
                    f"{KEY_PREFIX}:{c.id}",
                    mapping={
                        "program": c.program,
                        "source": c.source,
                        "text": c.text,
                        "vector": json.dumps(v),
                    },
                )
                pipe.sadd(self._ids_key, c.id)
        pipe.execute()
        self._size = len(chunks)
        return self._size

    def search(self, query: str, k: int = 4, program: str | None = None) -> list[Retrieved]:
        ids = self._r.smembers(self._ids_key)
        if not ids:
            return []
        qv = embed_one(query)
        results: list[Retrieved] = []
        for cid in ids:
            data = self._r.hgetall(f"{KEY_PREFIX}:{cid}")
            if not data or (program and data.get("program") != program):
                continue
            vec = json.loads(data["vector"])
            results.append(
                Retrieved(
                    text=data.get("text", ""),
                    program=data.get("program", ""),
                    source=data.get("source", ""),
                    score=_cosine(qv, vec),
                )
            )
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]


_index = None


def get_index():
    global _index
    if _index is not None:
        return _index
    settings = get_settings()
    if settings.has_redis:
        # Prefer native RediSearch vector KNN; fall back to Redis-backed brute force
        # if the Search module isn't installed on the DB.
        for cls in (RedisVLIndex, RedisKNNIndex):
            try:
                idx = cls(settings.redis_url)
                idx.build()
                _index = idx
                return _index
            except Exception:
                continue
    idx = RagIndex()
    idx.build()
    _index = idx
    return _index
