"""Load the RAG SOURCE corpus: data/knowledge/manifest.json + one .txt per document.

This is the authored program documentation the ingest embeds — the source of truth,
distinct from the embedded vectors in public.rag_chunks.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Iterator

from app.rag.scope import PolicyMetadata

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


def iter_sources() -> Iterator[SourceDoc]:
    """Yield source docs from the bundled manifest + .txt files."""
    manifest_path = os.path.join(KNOWLEDGE_DIR, "manifest.json")
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    for doc in manifest.get("docs", []):
        path = os.path.join(KNOWLEDGE_DIR, doc["text_path"])
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        # PDF extraction leaves NUL (0x00) bytes in the corpus. Postgres text columns
        # reject them, and the chunker strips them anyway (index._chunk_text).
        text = text.replace("\x00", "")
        yield SourceDoc(
            document_id=doc["document_id"],
            program=doc["program"],
            text=text,
            title=doc.get("title", ""),
            source_url=doc.get("source_url", ""),
            policy=PolicyMetadata.from_dict(doc, doc["program"]),
        )

