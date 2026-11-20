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
from collections import Counter

from app.rag.embeddings import batch_size, model_id
from app.rag.index import iter_documents, rebuild_index, sync_index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="re-embed every document instead of only the changed ones",
    )
    parser.add_argument("--metadata-only", action="store_true", help="Migrate/update document scope metadata without re-embedding")
    args = parser.parse_args()
    if args.rebuild and args.metadata_only:
        parser.error("--rebuild and --metadata-only cannot be combined")
    if args.metadata_only:
        from app.core.config import get_settings
        from app.rag.index import PgVectorIndex
        index = PgVectorIndex(get_settings().database_url)
        try:
            print(f"Updated scope metadata for {index.sync_metadata()} documents; vectors unchanged.")
        finally:
            index._pool.close()
        return
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    by_program: Counter[str] = Counter()
    docs = 0
    for doc in iter_documents():
        by_program[doc.program] += 1
        docs += 1
    print(f"Corpus: {docs} documents")
    for program, n in sorted(by_program.items()):
        print(f"  {program:16} {n:>3} documents")
    print(f"Embedding with {model_id()} (batch={batch_size()}) ...")

    if args.rebuild:
        index = rebuild_index()
        print(f"Done. backend={index.backend} rebuilt={index.size} chunks")
        return
    index, result = sync_index()
    print(
        f"Done. backend={index.backend} documents_reindexed={result.changed} "
        f"documents_removed={result.removed} chunks={result.total}"
    )


if __name__ == "__main__":
    from app.core.config import require_for
    require_for("rag-ingest")
    main()
