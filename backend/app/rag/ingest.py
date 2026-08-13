"""CLI that syncs the RAG vector index with the committed knowledge corpus.

This is the ONLY place the corpus is embedded; the serving container embeds one-line queries
and nothing else. It is incremental and idempotent: each document is stored with a
fingerprint of its text, the chunking parameters and the embedding model, so a run only
re-embeds documents whose fingerprint changed and deletes rows for documents that are gone.
Re-running against an unchanged corpus costs a single query.

Usage:
    DATABASE_URL=... python -m app.rag.ingest              # sync
    DATABASE_URL=... python -m app.rag.ingest --rebuild    # drop and re-embed everything
"""

import argparse
import logging
import sys
from collections import Counter

from ..config import get_settings
from .embeddings import batch_size, model_id, provider
from .index import iter_documents, rebuild_index, sync_index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="re-embed every document instead of only the changed ones",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not get_settings().has_postgres:
        # Otherwise the corpus is embedded into an in-memory index that dies with this
        # process — minutes of embedding, and the reported success writes nothing.
        sys.exit("DATABASE_URL is not set; there is nowhere to write the index.")

    by_program: Counter[str] = Counter()
    docs = 0
    for doc in iter_documents():
        by_program[doc.program] += 1
        docs += 1
    print(f"Corpus: {docs} documents")
    for program, n in sorted(by_program.items()):
        print(f"  {program:16} {n:>3} documents")
    print(f"Embedding with {provider()}/{model_id()} (batch={batch_size()}) ...")

    if args.rebuild:
        index = rebuild_index()
        print(f"Done. backend={index.backend} rebuilt={index.size} chunks")
        return
    index, result = sync_index()
    if result.changed < 0:  # backend can't diff; it was a full rebuild
        print(f"Done. backend={index.backend} rebuilt={result.total} chunks")
        return
    print(
        f"Done. backend={index.backend} documents_reindexed={result.changed} "
        f"documents_removed={result.removed} chunks={result.total}"
    )


if __name__ == "__main__":
    main()
