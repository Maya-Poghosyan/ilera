"""Load the RAG SOURCE corpus from the `reference.rag_sources` table.

This is the authored program documentation the ingest embeds — the source of truth,
distinct from the embedded vectors in public.rag_chunks. Read path is DB-first with a
file fallback to data/knowledge/ (manifest.json + per-doc .txt), the same discipline as
the other reference loaders.

Each row carries the manifest metadata (program, title, source_url, full meta) and the
document's source text. Seeding reads the bundled manifest + text files and upserts.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Iterator

from .. import db
from .scope import PolicyMetadata

logger = logging.getLogger("ilera.rag.source_store")

_DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data")
KNOWLEDGE_DIR = os.path.join(_DATA, "knowledge")


@dataclass
class SourceDoc:
    document_id: str
    program: str
    text: str
    title: str = ""
    source_url: str = ""
    policy: PolicyMetadata = field(default_factory=PolicyMetadata)


# ── File (seed) side ─────────────────────────────────────────────────────────


def iter_source_files() -> Iterator[SourceDoc]:
    """Yield source docs from the bundled manifest + .txt files, if present."""
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
        # PDF extraction leaves NUL (0x00) bytes in the corpus. Postgres text columns
        # reject them, and the chunker strips them anyway (index._chunk_text), so strip
        # at the source for both the DB seed and the file-fallback path — keeping the two
        # byte-identical. (The embedded chunks were already NUL-free, so retrieval is
        # unchanged; only the stored source representation is normalized.)
        text = text.replace("\x00", "")
        yield SourceDoc(
            document_id=doc["document_id"],
            program=doc["program"],
            text=text,
            title=doc.get("title", ""),
            source_url=doc.get("source_url", ""),
            policy=PolicyMetadata.from_dict(doc, doc["program"]),
        )


def _manifest_entries() -> dict[str, dict]:
    manifest_path = os.path.join(KNOWLEDGE_DIR, "manifest.json")
    if not os.path.exists(manifest_path):
        return {}
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    return {d["document_id"]: d for d in manifest.get("docs", [])}


# ── DB side ──────────────────────────────────────────────────────────────────


def seed_rag_sources_from_files() -> int:
    """Upsert the bundled corpus source into reference.rag_sources. Idempotent."""
    if not db.available():
        return 0
    entries = _manifest_entries()
    n = 0
    with db.connection() as conn:
        for doc in iter_source_files():
            meta = entries.get(doc.document_id, {})
            conn.execute(
                "INSERT INTO reference.rag_sources "
                "(document_id, program, title, source_url, meta, text) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s) "
                "ON CONFLICT (document_id) DO UPDATE SET "
                "program = EXCLUDED.program, title = EXCLUDED.title, "
                "source_url = EXCLUDED.source_url, meta = EXCLUDED.meta, "
                "text = EXCLUDED.text, updated_at = now()",
                (doc.document_id, doc.program, doc.title, doc.source_url,
                 json.dumps(meta), doc.text),
            )
            n += 1
    if n:
        logger.info("Seeded %d RAG source documents into reference.rag_sources", n)
    return n


def _db_has_sources() -> bool:
    if not db.available():
        return False
    try:
        with db.connection() as conn:
            row = conn.execute("SELECT 1 FROM reference.rag_sources LIMIT 1").fetchone()
        return row is not None
    except Exception:
        return False


def iter_sources() -> Iterator[SourceDoc]:
    """Yield the RAG source corpus, DB-first with a file fallback."""
    if _db_has_sources():
        bundled = _manifest_entries()
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT document_id, program, title, source_url, text, meta "
                "FROM reference.rag_sources ORDER BY document_id"
            ).fetchall()
        for document_id, program, title, source_url, text, meta in rows:
            # Backfill only newly introduced scope fields for known bundled documents.
            # Explicit DB metadata wins, including an empty jurisdiction list.
            metadata = {**bundled.get(document_id, {}), **(meta or {})}
            yield SourceDoc(document_id, program, text, title or "", source_url or "",
                            PolicyMetadata.from_dict(metadata, program))
        return
    yield from iter_source_files()
