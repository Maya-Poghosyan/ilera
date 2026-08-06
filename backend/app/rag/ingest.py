"""CLI to (re)build the RAG vector index from the committed knowledge corpus.

This is the ONLY place the corpus should be embedded. Run it once against the store
(`DATABASE_URL` / `REDIS_URL`) after the corpus or the embedding model changes; the serving
container then only embeds one-line queries.

Usage:
    DATABASE_URL=... python -m app.rag.ingest
"""

import logging
from collections import Counter

from .embeddings import batch_size, provider
from .index import iter_chunks, rebuild_index


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    by_program: Counter[str] = Counter()
    docs: set[str] = set()
    total = 0
    for chunk in iter_chunks():
        by_program[chunk.program] += 1
        docs.add(chunk.document_id or chunk.source)
        total += 1
    print(f"Loaded {total} chunks from {len(docs)} documents")
    for program, n in sorted(by_program.items()):
        print(f"  {program:16} {n:>5} chunks")
    print(f"Embedding + indexing (provider={provider()}, batch={batch_size()}) ...")
    index = rebuild_index()
    print(f"Done. backend={index.backend} indexed={index.size}")


if __name__ == "__main__":
    main()
