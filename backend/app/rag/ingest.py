"""CLI to (re)build the RAG vector index from the committed knowledge corpus.

Usage:
    python -m app.rag.ingest
"""

from collections import Counter

from .index import iter_chunks, rebuild_index


def main() -> None:
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
    print("Embedding + indexing ...")
    index = rebuild_index()
    print(f"Done. backend={index.backend} indexed={index.size}")


if __name__ == "__main__":
    main()
