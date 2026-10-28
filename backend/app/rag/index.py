"""RAG index over official program documentation.

Two backends with the same interface:
- PgVectorIndex: chunks + vectors in Postgres, ANN in the database (used when DATABASE_URL is set).
- RagIndex: in-memory cosine fallback (no infrastructure needed).

Building an index means embedding the whole corpus, which is expensive in memory and time, so
it happens only in the offline `app.rag.ingest` step. A serving process attaches to whatever
the ingest already wrote and never builds: `ensure()` reports an empty index rather than
embedding on demand, and `build()` is reachable only through `rebuild_index()`.
"""

from __future__ import annotations

import glob
import hashlib
import json
import logging
import os
import re
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field

from ..config import get_settings
from .embeddings import dim, embed, embed_one
from .embeddings import model_id as embedding_id
from .embeddings import provider as embedding_provider
from .scope import PolicyMetadata, RetrievalScope

_DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data")
KNOWLEDGE_DIR = os.path.join(_DATA, "knowledge")
DATA_DIR = os.path.join(_DATA, "program_docs")  # legacy sample docs (fallback)
CHUNK_CHARS = 1400
CHUNK_OVERLAP = 200
_PAGE_RE = re.compile(r"\[page (\d+)\]")

logger = logging.getLogger(__name__)


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
    policy: PolicyMetadata = field(default_factory=PolicyMetadata)


@dataclass
class Document:
    """One source document, the unit the corpus is versioned and re-embedded in."""

    document_id: str
    program: str
    text: str
    title: str = ""
    source_url: str = ""
    legacy: bool = False
    policy: PolicyMetadata = field(default_factory=PolicyMetadata)

    def chunks(self) -> list[Chunk]:
        if self.legacy:
            text = self.text.replace("\x00", "")
            return [
                Chunk(id=f"{self.program}:{i}", program=self.program, text=piece,
                      source=self.document_id, document_id=self.document_id, policy=self.policy)
                for i in range(0, len(text), CHUNK_CHARS)
                if (piece := text[i : i + CHUNK_CHARS].strip())
            ]
        return [
            Chunk(
                id=f"{self.document_id}:{n}",
                program=self.program,
                text=piece,
                source=self.document_id,
                title=self.title,
                source_url=self.source_url,
                document_id=self.document_id,
                page=str(page),
                policy=self.policy,
            )
            for n, (piece, page) in enumerate(_chunk_text(self.text))
        ]

    def fingerprint(self) -> str:
        """Identifies the *indexed form* of this document, not just its bytes.

        Chunking parameters and the embedding model are part of it, so changing either
        invalidates every document and the next ingest re-embeds the corpus instead of
        leaving vectors that silently can't be compared.
        """
        h = hashlib.sha256()
        for part in (self.text, self.program, self.title, self.source_url,
                     str(CHUNK_CHARS), str(CHUNK_OVERLAP), embedding_provider(), embedding_id()):
            h.update(part.encode("utf-8"))
            h.update(b"\x1f")
        return h.hexdigest()


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
    policy: dict = field(default_factory=dict)


def _chunk_text(text: str) -> list[tuple[str, str]]:
    """Split into overlapping windows, tracking the most recent [page N] marker."""
    # PDF extraction leaves NUL bytes in the corpus, which Postgres text columns reject.
    text = text.replace("\x00", "")
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


def _iter_corpus_documents() -> Iterator[Document]:
    """The authored RAG corpus, DB-first (reference.rag_sources) with a file fallback.

    Source of truth moved into Postgres; this maps each source row/file to the Document
    the chunker consumes. The embedded vectors remain in public.rag_chunks.
    """
    from .source_store import iter_sources

    for src in iter_sources():
        yield Document(
            document_id=src.document_id,
            program=src.program,
            text=src.text,
            title=src.title,
            source_url=src.source_url,
            policy=src.policy,
        )


def _iter_legacy_documents() -> Iterator[Document]:
    for path in glob.glob(os.path.join(DATA_DIR, "*.txt")):
        program = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as fh:
            yield Document(
                document_id=os.path.basename(path), program=program, text=fh.read(), legacy=True
            )


def iter_documents() -> Iterator[Document]:
    """Stream the real knowledge corpus when present, else the bundled sample docs.

    A generator, so indexing holds one document (and its chunks) at a time rather than the
    whole corpus.
    """
    corpus = _iter_corpus_documents()
    first = next(corpus, None)
    if first is None:
        yield from _iter_legacy_documents()
        return
    yield first
    yield from corpus


def iter_chunks() -> Iterator[Chunk]:
    for doc in iter_documents():
        yield from doc.chunks()


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


def _embedded(chunks: list[Chunk]) -> Iterator[list[tuple[Chunk, list[float]]]]:
    """Same, for the chunks of a single document (the unit an incremental sync rewrites)."""
    size = max(1, get_settings().index_write_batch_size)
    for i in range(0, len(chunks), size):
        window = chunks[i : i + size]
        yield list(zip(window, embed([c.text for c in window])))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


@dataclass
class SyncResult:
    changed: int
    removed: int
    total: int


def _no_build(backend: str) -> int:
    """Report an empty index instead of embedding the corpus on the spot.

    Ingest is an offline step: a serving process that builds on demand pays hundreds of MB
    and minutes of latency inside a request, which is what OOMed the container.
    """
    logger.error(
        "RAG index (%s) is empty — retrieval will return nothing until "
        "`python -m app.rag.ingest` has been run against this store.",
        backend,
    )
    return 0


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
        if self._chunks:
            return len(self._chunks)
        return _no_build(self.backend)

    def search(self, query: str, k: int = 4, *, scope: RetrievalScope) -> list[Retrieved]:
        if not self._chunks:
            return []
        qv = embed_one(query)
        results = [
            Retrieved(
                text=c.text, program=c.program, source=c.source, score=_cosine(qv, c.vector),
                title=c.title, source_url=c.source_url, document_id=c.document_id, page=c.page,
                policy=c.policy.evidence(),
            )
            for c in self._chunks
            if c.policy.allows(scope)
        ]
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]



class PgVectorIndex:
    """Chunks + vectors in Postgres; KNN in the database via pgvector.

    Preferred backend: the chunk text lives in a column instead of this process's heap, the
    ANN search runs server-side and returns only the k rows asked for, and the corpus is
    ingested once (offline) rather than rebuilt whenever the store comes up empty.
    """

    backend = "pgvector"
    TABLE = "rag_chunks"

    def __init__(self, dsn: str) -> None:
        from psycopg_pool import ConnectionPool

        self._dim = dim()
        # Searches arrive from several agent worker threads at once, so hand each one its own
        # connection rather than sharing (a psycopg connection is not concurrently usable).
        self._pool = ConnectionPool(dsn, min_size=1, max_size=4, open=True, timeout=15)
        self._size = 0

    @property
    def size(self) -> int:
        return self._size

    def _count(self) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = %s",
                (self.TABLE,),
            ).fetchone()
            if not row or not row[0]:
                return 0
            row = conn.execute(f"SELECT count(*) FROM {self.TABLE}").fetchone()  # noqa: S608
            return int(row[0]) if row else 0

    def ensure(self) -> int:
        n = self._count()
        if n:
            self._check_dim()
            with self._pool.connection() as conn:
                row = conn.execute("SELECT to_regclass('rag_document_scopes')").fetchone()
            if not row or row[0] is None:
                raise RuntimeError("Policy scope catalog missing; run app.rag.ingest --metadata-only before serving.")
            self._size = n
            return n
        return _no_build(self.backend)

    def _check_dim(self) -> None:
        """An index ingested with a different embedding model is useless, and the only symptom
        is bad answers, so say so loudly at startup rather than at query time."""
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT atttypmod FROM pg_attribute WHERE attrelid = %s::regclass "
                "AND attname = 'embedding'",
                (self.TABLE,),
            ).fetchone()
        stored = int(row[0]) if row and row[0] and row[0] > 0 else 0
        if stored and stored != self._dim:
            logger.error(
                "RAG index was built with %d-dim vectors but %s produces %d — re-run "
                "`python -m app.rag.ingest`; searches will fail until you do.",
                stored, embedding_provider(), self._dim,
            )

    def _stored_dim(self, conn) -> int:
        row = conn.execute(
            "SELECT atttypmod FROM pg_attribute WHERE attrelid = to_regclass(%s) "
            "AND attname = 'embedding'",
            (self.TABLE,),
        ).fetchone()
        return int(row[0]) if row and row[0] and row[0] > 0 else 0

    def _create_schema(self, conn) -> None:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(f"DROP TABLE IF EXISTS {self.TABLE}")  # noqa: S608
        conn.execute(
            f"""
            CREATE TABLE {self.TABLE} (
                id          text PRIMARY KEY,
                program     text NOT NULL,
                source      text NOT NULL DEFAULT '',
                title       text NOT NULL DEFAULT '',
                source_url  text NOT NULL DEFAULT '',
                document_id text NOT NULL DEFAULT '',
                page        text NOT NULL DEFAULT '',
                doc_hash    text NOT NULL DEFAULT '',
                text        text NOT NULL,
                embedding   vector({self._dim}) NOT NULL
            )
            """  # noqa: S608
        )
        # HNSW is cheaper to build in one pass than to maintain across thousands of inserts,
        # but a sync writes a handful of documents into an existing table, so it has to exist
        # up front rather than being created after the load.
        conn.execute(
            f"CREATE INDEX ON {self.TABLE} USING hnsw (embedding vector_cosine_ops)"  # noqa: S608
        )
        conn.execute(f"CREATE INDEX ON {self.TABLE} (program)")  # noqa: S608
        conn.execute(f"CREATE INDEX ON {self.TABLE} (document_id)")  # noqa: S608

    def _create_scope_schema(self, conn) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rag_document_scopes (
                document_id text PRIMARY KEY,
                applicable_programs text[] NOT NULL,
                jurisdictions text[] NOT NULL,
                effective_from date,
                effective_to date,
                authority_level text NOT NULL DEFAULT '',
                version text NOT NULL DEFAULT '',
                CHECK (effective_from IS NULL OR effective_to IS NULL OR effective_to > effective_from)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS rag_scope_programs ON rag_document_scopes USING gin (applicable_programs)")
        conn.execute("CREATE INDEX IF NOT EXISTS rag_scope_jurisdictions ON rag_document_scopes USING gin (jurisdictions)")

    def _write_scope(self, conn, doc: Document) -> None:
        policy = doc.policy
        if not policy.jurisdictions:
            logger.warning("Excluding unclassified document from retrieval: %s", doc.document_id)
        conn.execute("""
            INSERT INTO rag_document_scopes
                (document_id, applicable_programs, jurisdictions, effective_from,
                 effective_to, authority_level, version)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (document_id) DO UPDATE SET
                applicable_programs = EXCLUDED.applicable_programs,
                jurisdictions = EXCLUDED.jurisdictions,
                effective_from = EXCLUDED.effective_from,
                effective_to = EXCLUDED.effective_to,
                authority_level = EXCLUDED.authority_level,
                version = EXCLUDED.version
        """, (doc.document_id, list(policy.applicable_programs), list(policy.jurisdictions),
              policy.effective_from, policy.effective_to, policy.authority_level, policy.version))

    def sync_metadata(self) -> int:
        """Add/update scope metadata without changing vectors or source text."""
        docs = list(iter_documents())  # validate all metadata before starting writes
        with self._pool.connection() as conn:
            self._create_scope_schema(conn)
            for doc in docs:
                self._write_scope(conn, doc)
        return len(docs)

    def _write_document(self, conn, doc: Document, fingerprint: str) -> int:
        """Replace one document's rows. Delete-then-insert so removed chunks don't linger."""
        conn.execute(f"DELETE FROM {self.TABLE} WHERE document_id = %s", (doc.document_id,))  # noqa: S608
        written = 0
        with conn.cursor() as cur:
            for batch in _embedded(doc.chunks()):
                cur.executemany(
                    f"INSERT INTO {self.TABLE} (id, program, source, title, source_url, "  # noqa: S608
                    "document_id, page, doc_hash, text, embedding) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [
                        (
                            c.id, c.program, c.source, c.title, c.source_url,
                            c.document_id, c.page, fingerprint, c.text, _vector_literal(v),
                        )
                        for c, v in batch
                    ],
                )
                written += len(batch)
        return written

    def build(self) -> int:
        with self._pool.connection() as conn:
            self._create_schema(conn)
            self._create_scope_schema(conn)
            for doc in iter_documents():
                self._write_scope(conn, doc)
                self._write_document(conn, doc, doc.fingerprint())
        self._size = self._count()
        return self._size

    def sync(self) -> "SyncResult":
        """Bring the store in line with the corpus, embedding only what changed.

        Documents carry the fingerprint they were indexed under, so an unchanged corpus costs
        one query and no embedding calls — which is what makes it safe to run this on every
        merge rather than hand-triggering a 17-minute rebuild.
        """
        with self._pool.connection() as conn:
            self._create_scope_schema(conn)
            stored_dim = self._stored_dim(conn)
            if stored_dim and stored_dim != self._dim:
                # A different-width vector column can't be written into or compared against.
                logger.warning(
                    "Index holds %d-dim vectors but %s produces %d — rebuilding from scratch",
                    stored_dim, embedding_id(), self._dim,
                )
                stored_dim = 0
            if not stored_dim:
                self._create_schema(conn)
                existing: dict[str, str] = {}
            else:
                existing = dict(
                    conn.execute(
                        f"SELECT document_id, min(doc_hash) FROM {self.TABLE} GROUP BY 1"  # noqa: S608
                    ).fetchall()
                )
            changed = 0
            seen: set[str] = set()
            for doc in iter_documents():
                self._write_scope(conn, doc)
                seen.add(doc.document_id)
                fingerprint = doc.fingerprint()
                if existing.get(doc.document_id) == fingerprint:
                    continue
                logger.info("Indexing %s", doc.document_id)
                self._write_document(conn, doc, fingerprint)
                changed += 1
            removed = sorted(set(existing) - seen)
            if removed:
                conn.execute(
                    f"DELETE FROM {self.TABLE} WHERE document_id = ANY(%s)", (removed,)  # noqa: S608
                )
        self._size = self._count()
        return SyncResult(changed=changed, removed=len(removed), total=self._size)

    def search(self, query: str, k: int = 4, *, scope: RetrievalScope) -> list[Retrieved]:
        if not self._size:
            return []  # never ingested: the table may not even exist
        qv = _vector_literal(embed_one(query))
        # Materialize the eligible subset before ranking. A global ANN scan followed
        # by selective state/program filters can underfill top-k and lose relevant hits.
        # Exact ranking is deliberate for today's corpus; benchmark partitions before
        # switching to approximate search as it grows.
        sql = f"""
            WITH eligible AS MATERIALIZED (
                SELECT c.*, m.applicable_programs, m.jurisdictions, m.effective_from,
                       m.effective_to, m.authority_level, m.version
                FROM {self.TABLE} c JOIN rag_document_scopes m USING (document_id)
                WHERE m.applicable_programs @> %s::text[]
                  AND m.jurisdictions && %s::text[]
                  AND (m.effective_from IS NULL OR m.effective_from <= %s::date)
                  AND (m.effective_to IS NULL OR %s::date < m.effective_to)
            )
            SELECT text, program, source, title, source_url, document_id, page,
                   1 - (embedding <=> %s::vector), applicable_programs, jurisdictions,
                   effective_from, effective_to, authority_level, version
            FROM eligible ORDER BY embedding <=> %s::vector LIMIT %s
        """
        params = [[scope.program], scope.jurisdictions, scope.as_of, scope.as_of, qv, qv, k]
        with self._pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            Retrieved(
                text=r[0], program=r[1], source=r[2], title=r[3], source_url=r[4],
                document_id=r[5], page=r[6], score=float(r[7]),
                policy=PolicyMetadata(tuple(r[8]), tuple(r[9]), r[10], r[11], r[12], r[13]).evidence(),
            )
            for r in rows
        ]


def _vector_literal(vector: list[float]) -> str:
    """pgvector's text input format, so no extra client-side type adapter is needed."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


_index = None
# Serializes index construction. Every specialist agent looks documents up through its own
# worker thread, so an unguarded lazy build let the whole panel start a full corpus embed at
# the same moment — N concurrent builds, N times the peak memory.
_index_lock = threading.Lock()


def _make_index(*, force: bool):
    """Attach to the store the ingest wrote to. `force` (ingest only) rebuilds it in place."""
    settings = get_settings()
    if settings.has_postgres:
        if force:
            # An explicit ingest must not quietly land somewhere else.
            idx = PgVectorIndex(settings.database_url)
            idx.build()
            return idx
        idx = PgVectorIndex(settings.database_url)
        try:
            idx.ensure()
        except Exception:
            idx._pool.close()
            raise
        return idx
    idx = RagIndex()
    idx.build() if force else idx.ensure()
    return idx


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


def sync_index() -> tuple[object, SyncResult]:
    """Bring the active backend in line with the corpus, re-embedding only what changed.

    Only pgvector tracks per-document fingerprints; the in-memory backend has no way to tell
    what changed, so for it this is a full rebuild.
    """
    global _index
    with _index_lock:
        settings = get_settings()
        if settings.has_postgres:
            idx = PgVectorIndex(settings.database_url)
            result = idx.sync()
        else:
            idx = _make_index(force=True)
            result = SyncResult(changed=-1, removed=0, total=idx.size)
        _index = idx
    return idx, result
