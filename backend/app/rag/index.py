"""RAG index over official program documentation.

Two backends with the same interface:
- RedisVLIndex: vectors stored in Redis, KNN via RediSearch (used when REDIS_URL is set).
- RagIndex: in-memory cosine fallback (no infrastructure needed).
"""

import glob
import heapq
import json
import os
import re
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field

from ..config import get_settings
from .embeddings import dim, embed, embed_one

_DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data")
KNOWLEDGE_DIR = os.path.join(_DATA, "knowledge")
DATA_DIR = os.path.join(_DATA, "program_docs")  # legacy sample docs (fallback)
CHUNK_CHARS = 1400
CHUNK_OVERLAP = 200
INDEX_NAME = "ilera_docs"
KEY_PREFIX = "ilera:doc"
_PAGE_RE = re.compile(r"\[page (\d+)\]")


@dataclass
class Chunk:
    id: str
    program: str
    text: str
    source: str
    title: str = ""
    source_url: str = ""
    document_id: str = ""
    page: str = ""
    vector: list[float] = field(default_factory=list)


@dataclass
class Retrieved:
    text: str
    program: str
    source: str
    score: float
    title: str = ""
    source_url: str = ""
    document_id: str = ""
    page: str = ""


def _chunk_text(text: str) -> list[tuple[str, str]]:
    """Split into overlapping windows, tracking the most recent [page N] marker."""
    out: list[tuple[str, str]] = []
    step = max(1, CHUNK_CHARS - CHUNK_OVERLAP)
    for i in range(0, len(text), step):
        piece = text[i : i + CHUNK_CHARS].strip()
        if not piece:
            continue
        pages = _PAGE_RE.findall(text[:i + CHUNK_CHARS])
        page = pages[-1] if pages else ""
        cleaned = _PAGE_RE.sub("", piece).strip()
        if cleaned:
            out.append((cleaned, page))
    return out


def _iter_corpus_chunks() -> Iterator[Chunk]:
    manifest_path = os.path.join(KNOWLEDGE_DIR, "manifest.json")
    if not os.path.exists(manifest_path):
        return
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    for doc in manifest.get("docs", []):
        path = os.path.join(KNOWLEDGE_DIR, doc["text_path"])
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for n, (piece, page) in enumerate(_chunk_text(text)):
            yield Chunk(
                id=f"{doc['document_id']}:{n}",
                program=doc["program"],
                text=piece,
                source=doc["document_id"],
                title=doc.get("title", ""),
                source_url=doc.get("source_url", ""),
                document_id=doc["document_id"],
                page=str(page),
            )


def _iter_legacy_chunks() -> Iterator[Chunk]:
    for path in glob.glob(os.path.join(DATA_DIR, "*.txt")):
        program = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for i in range(0, len(text), CHUNK_CHARS):
            piece = text[i : i + CHUNK_CHARS].strip()
            if piece:
                yield Chunk(id=f"{program}:{i}", program=program, text=piece,
                            source=os.path.basename(path))


def iter_chunks() -> Iterator[Chunk]:
    """Stream the real knowledge corpus when present, else the bundled sample docs.

    A generator so an index build never holds the whole corpus (documents + chunk text)
    in memory at once.
    """
    corpus = _iter_corpus_chunks()
    first = next(corpus, None)
    if first is None:
        yield from _iter_legacy_chunks()
        return
    yield first
    yield from corpus


def load_chunks() -> list[Chunk]:
    """Materialize the whole corpus. Prefer `iter_chunks` on the indexing path."""
    return list(iter_chunks())


def _embedded_batches() -> Iterator[list[tuple[Chunk, list[float]]]]:
    """Stream the corpus as (chunk, vector) batches ready to be written to a backend.

    Bounded memory by construction: only `index_write_batch_size` chunks and their vectors
    exist at a time (and `embed` splits each window into smaller forward passes), instead of
    holding every chunk, every vector, and a full write payload simultaneously.
    """
    size = max(1, get_settings().index_write_batch_size)
    window: list[Chunk] = []
    for chunk in iter_chunks():
        window.append(chunk)
        if len(window) >= size:
            yield list(zip(window, embed([c.text for c in window])))
            window = []
    if window:
        yield list(zip(window, embed([c.text for c in window])))


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
        chunks: list[Chunk] = []
        for batch in _embedded_batches():
            for c, v in batch:
                c.vector = v
                chunks.append(c)
        self._chunks = chunks
        return len(chunks)

    def ensure(self) -> int:
        return self.build() if not self._chunks else len(self._chunks)

    def search(self, query: str, k: int = 4, program: str | None = None) -> list[Retrieved]:
        if not self._chunks:
            return []
        qv = embed_one(query)
        results = [
            Retrieved(
                text=c.text, program=c.program, source=c.source, score=_cosine(qv, c.vector),
                title=c.title, source_url=c.source_url, document_id=c.document_id, page=c.page,
            )
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
                    {"name": "title", "type": "text"},
                    {"name": "source_url", "type": "text"},
                    {"name": "document_id", "type": "tag"},
                    {"name": "page", "type": "text"},
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

    def ensure(self) -> int:
        try:
            n = int(self._index.info().get("num_docs", 0))
        except Exception:
            n = 0
        if n:
            self._size = n
            return n
        return self.build()

    def build(self) -> int:
        from redisvl.redis.utils import array_to_buffer

        self._index.create(overwrite=True, drop=True)
        written = 0
        for batch in _embedded_batches():
            self._index.load(
                [
                    {
                        "id": c.id,
                        "program": c.program,
                        "source": c.source,
                        "title": c.title,
                        "source_url": c.source_url,
                        "document_id": c.document_id,
                        "page": c.page,
                        "text": c.text,
                        "vector": array_to_buffer(v, dtype="float32"),
                    }
                    for c, v in batch
                ],
                id_field="id",
            )
            written += len(batch)
        self._size = written
        return self._size

    def search(self, query: str, k: int = 4, program: str | None = None) -> list[Retrieved]:
        from redisvl.query import VectorQuery
        from redisvl.query.filter import Tag

        qv = embed_one(query)
        vq = VectorQuery(
            vector=qv,
            vector_field_name="vector",
            return_fields=["program", "source", "title", "source_url", "document_id", "page", "text"],
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
                    title=r.get("title", ""),
                    source_url=r.get("source_url", ""),
                    document_id=r.get("document_id", ""),
                    page=r.get("page", ""),
                )
            )
        return out


class RedisVectorSetIndex:
    """Native Redis 8 Vector Sets (VADD/VSIM) — server-side vector KNN.

    Used when the DB has the `vectorset` module (Redis >= 8) but not RediSearch.
    Each chunk is one vector-set element; program/source/text live in its JSON attributes,
    and program filtering uses VSIM's FILTER expression.
    """

    backend = "redis-vectorset"
    SET_KEY = f"{KEY_PREFIX}:vset"

    def __init__(self, redis_url: str) -> None:
        import redis

        self._r = redis.from_url(redis_url, decode_responses=True, socket_timeout=8)
        # Fail fast if the vectorset module is missing so get_index() can fall back.
        names = {m[1] for m in self._r.execute_command("MODULE", "LIST")}
        if "vectorset" not in names:
            raise RuntimeError("vectorset module not available")
        self._size = 0

    @property
    def size(self) -> int:
        return self._size

    def ensure(self) -> int:
        n = int(self._r.execute_command("VCARD", self.SET_KEY)) if self._r.exists(self.SET_KEY) else 0
        if n:
            self._size = n
            return n
        return self.build()

    def build(self) -> int:
        self._r.delete(self.SET_KEY)
        written = 0
        for batch in _embedded_batches():
            pipe = self._r.pipeline(transaction=False)
            for c, v in batch:
                attrs = json.dumps({
                    "program": c.program, "source": c.source, "text": c.text,
                    "title": c.title, "source_url": c.source_url,
                    "document_id": c.document_id, "page": c.page,
                })
                pipe.execute_command(
                    "VADD", self.SET_KEY, "VALUES", len(v), *v, c.id, "SETATTR", attrs
                )
            pipe.execute()
            written += len(batch)
        self._size = written
        return self._size

    def search(self, query: str, k: int = 4, program: str | None = None) -> list[Retrieved]:
        if not self._r.exists(self.SET_KEY):
            return []
        qv = embed_one(query)
        args = ["VSIM", self.SET_KEY, "VALUES", len(qv), *qv, "WITHSCORES", "COUNT", k]
        if program:
            args += ["FILTER", f'.program=="{program}"']
        rows = self._r.execute_command(*args)
        out: list[Retrieved] = []
        for i in range(0, len(rows), 2):
            element, score = rows[i], float(rows[i + 1])
            attrs = json.loads(self._r.execute_command("VGETATTR", self.SET_KEY, element) or "{}")
            out.append(
                Retrieved(
                    text=attrs.get("text", ""),
                    program=attrs.get("program", ""),
                    source=attrs.get("source", ""),
                    score=score,
                    title=attrs.get("title", ""),
                    source_url=attrs.get("source_url", ""),
                    document_id=attrs.get("document_id", ""),
                    page=attrs.get("page", ""),
                )
            )
        return out


class RedisKNNIndex:
    """Vectors + metadata stored in Redis hashes; cosine ranking in Python.

    Works on any Redis (no special module required). Last-resort Redis backend when neither
    RediSearch nor Vector Sets are available.
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

    def ensure(self) -> int:
        n = int(self._r.scard(self._ids_key) or 0)
        if n:
            self._size = n
            return n
        return self.build()

    def build(self) -> int:
        pipe = self._r.pipeline(transaction=False)
        for cid in self._r.smembers(self._ids_key):
            pipe.delete(f"{KEY_PREFIX}:{cid}")
        pipe.delete(self._ids_key)
        pipe.execute()
        written = 0
        for batch in _embedded_batches():
            pipe = self._r.pipeline(transaction=False)
            for c, v in batch:
                pipe.hset(
                    f"{KEY_PREFIX}:{c.id}",
                    mapping={
                        "program": c.program,
                        "source": c.source,
                        "title": c.title,
                        "source_url": c.source_url,
                        "document_id": c.document_id,
                        "page": c.page,
                        "text": c.text,
                        "vector": json.dumps(v),
                    },
                )
                pipe.sadd(self._ids_key, c.id)
            pipe.execute()
            written += len(batch)
        self._size = written
        return self._size

    def search(self, query: str, k: int = 4, program: str | None = None) -> list[Retrieved]:
        """Brute-force scan, but only ever holding one batch of rows and the current top k.

        Every scored chunk carries its full text, so materializing the whole corpus per query
        (and one round trip per chunk) is what makes this backend expensive — with several
        specialists querying concurrently it dominates the process's memory.
        """
        ids = sorted(self._r.smembers(self._ids_key))
        if not ids:
            return []
        qv = embed_one(query)
        batch = max(1, get_settings().index_write_batch_size)
        best: list[tuple[float, int, Retrieved]] = []
        seq = 0
        for start in range(0, len(ids), batch):
            pipe = self._r.pipeline(transaction=False)
            for cid in ids[start : start + batch]:
                pipe.hgetall(f"{KEY_PREFIX}:{cid}")
            for data in pipe.execute():
                if not data or (program and data.get("program") != program):
                    continue
                score = _cosine(qv, json.loads(data["vector"]))
                if len(best) == k and score <= best[0][0]:
                    continue
                seq += 1
                heapq.heappush(
                    best,
                    (
                        score,
                        seq,
                        Retrieved(
                            text=data.get("text", ""),
                            program=data.get("program", ""),
                            source=data.get("source", ""),
                            score=score,
                            title=data.get("title", ""),
                            source_url=data.get("source_url", ""),
                            document_id=data.get("document_id", ""),
                            page=data.get("page", ""),
                        ),
                    ),
                )
                if len(best) > k:
                    heapq.heappop(best)
        return [r for _, _, r in sorted(best, key=lambda t: t[0], reverse=True)]


_index = None
# Serializes index construction. Every specialist agent looks documents up through its own
# worker thread, so an unguarded lazy build let the whole panel start a full corpus embed at
# the same moment — N concurrent builds, N times the peak memory.
_index_lock = threading.Lock()


def _make_index(*, force: bool):
    settings = get_settings()
    if settings.has_redis:
        # Prefer native server-side vector KNN (RediSearch or Redis 8 Vector Sets);
        # fall back to a Redis-backed brute-force index if neither module is present.
        for cls in (RedisVLIndex, RedisVectorSetIndex, RedisKNNIndex):
            try:
                idx = cls(settings.redis_url)
                if force:
                    idx.build()
                else:
                    idx.ensure()
                return idx
            except Exception:
                continue
    idx = RagIndex()
    if force:
        idx.build()
    else:
        idx.ensure()
    return idx


def current_index():
    """The already-built index, or None. Never triggers a build — for status endpoints that
    must not pay for (or allocate) a cold ingest."""
    return _index


def get_index():
    global _index
    if _index is not None:
        return _index
    with _index_lock:
        if _index is None:
            _index = _make_index(force=False)
    return _index


def rebuild_index():
    """Force a full re-ingest of the corpus into the active backend."""
    global _index
    with _index_lock:
        _index = _make_index(force=True)
    return _index
