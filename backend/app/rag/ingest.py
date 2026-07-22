"""CLI to (re)build the RAG vector index from the committed knowledge corpus.

Usage:
    python -m app.rag.ingest
"""

from collections import Counter

from .index import load_chunks, rebuild_index


def main() -> None:
    chunks = load_chunks()
    by_program = Counter(c.program for c in chunks)
    docs = len({c.document_id or c.source for c in chunks})
    print(f"Loaded {len(chunks)} chunks from {docs} documents")
    for program, n in sorted(by_program.items()):
        print(f"  {program:16} {n:>5} chunks")
    print("Embedding + indexing ...")
    index = rebuild_index()
    print(f"Done. backend={index.backend} indexed={index.size}")


if __name__ == "__main__":
    main()
