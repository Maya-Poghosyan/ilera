"""Guards for the indexing path that OOMed the container.

Embedding the corpus costs hundreds of MB and minutes; it belongs in `app.rag.ingest`, run
offline against the store. These tests pin the two invariants that keep it out of a serving
process: a cold index reports empty instead of building, and every provider embeds in
bounded batches.

"""
import os
from datetime import date
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings  # noqa: E402
from app.rag import embeddings, index  # noqa: E402


@pytest.fixture(autouse=True)
def offline_embedding_identity(monkeypatch):
    # Fingerprint tests exercise invalidation, not API access.
    monkeypatch.setattr(index, "embedding_id", lambda: "test-model")


def _reset_settings() -> None:
    get_settings.cache_clear()


def test_cold_index_reports_empty_instead_of_building(monkeypatch) -> None:
    """`build()` is reachable only from the ingest entry point (`rebuild_index`); attaching
    to a never-ingested store reports empty."""
    monkeypatch.setattr(index, "_index", None)
    monkeypatch.setattr(index.PgVectorIndex, "build",
                        lambda self: pytest.fail("serving path embedded the corpus"))
    monkeypatch.setattr(index.PgVectorIndex, "_count", lambda self: 0)
    idx = index.get_index()
    try:
        assert idx.size == 0
        assert idx.search("ihss hours", scope=index.RetrievalScope("ihss", "CA", date(2026, 10, 14))) == []
    finally:
        idx._pool.close()
        index._index = None


def test_embedding_batches_are_bounded(monkeypatch) -> None:
    """The OOM was one 3429-text forward pass; batch size must cap every call."""
    os.environ["EMBEDDING_API_BATCH_SIZE"] = "8"
    _reset_settings()
    try:
        sizes: list[int] = []
        monkeypatch.setattr(
            embeddings, "_embed_batch",
            lambda texts: sizes.append(len(texts)) or [[0.0]] * len(texts),
        )
        vectors = list(embeddings.embed_iter(str(i) for i in range(20)))
        assert len(vectors) == 20
        assert max(sizes) <= 8
    finally:
        os.environ.pop("EMBEDDING_API_BATCH_SIZE", None)
        _reset_settings()


def test_vector_literal_round_trips_pgvector_text_format() -> None:
    assert index._vector_literal([1.0, -0.5]) == "[1.0,-0.5]"


def _doc(text: str = "hello", **kw) -> index.Document:
    return index.Document(document_id="D1", program="ihss", text=text, **kw)


def test_fingerprint_is_stable_for_unchanged_documents() -> None:
    """What makes a sync cheap: same document, same fingerprint, no embedding call."""
    assert _doc().fingerprint() == _doc().fingerprint()
    assert _doc("hello").fingerprint() != _doc("hello!").fingerprint()


def test_fingerprint_tracks_the_embedding_model(monkeypatch) -> None:
    """Vectors from a different model are incomparable, so a model switch must invalidate
    every document rather than leaving a silently mixed index."""
    before = _doc().fingerprint()
    monkeypatch.setattr(index, "embedding_id", lambda: "text-embedding-3-large")
    assert _doc().fingerprint() != before


def test_fingerprint_tracks_chunking(monkeypatch) -> None:
    before = _doc().fingerprint()
    monkeypatch.setattr(index, "CHUNK_CHARS", index.CHUNK_CHARS + 1)
    assert _doc().fingerprint() != before


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
