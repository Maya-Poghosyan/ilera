"""Guards for the indexing path that OOMed the container.

Embedding the corpus costs hundreds of MB and minutes; it belongs in `app.rag.ingest`, run
offline against the store. These tests pin the two invariants that keep it out of a serving
process: a cold index reports empty instead of building, and every provider embeds in
bounded batches.

Runs with no services. Run directly or via pytest.
"""
import os
import sys

os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings  # noqa: E402
from app.rag import embeddings, index  # noqa: E402


def _reset_settings() -> None:
    get_settings.cache_clear()


def test_cold_index_reports_empty_instead_of_building() -> None:
    idx = index.RagIndex()
    calls: list[int] = []
    idx.build = lambda: calls.append(1) or 0  # type: ignore[method-assign]
    assert idx.ensure() == 0
    assert not calls, "a serving process must never embed the corpus on demand"
    assert idx.search("ihss hours") == []


def test_get_index_never_builds(monkeypatch) -> None:
    """`build()` is reachable only from the ingest entry point (`rebuild_index`)."""
    monkeypatch.setattr(index, "_index", None)
    monkeypatch.setattr(
        index, "_embedded_batches",
        lambda: (_ for _ in ()).throw(AssertionError("serving path embedded the corpus")),
    )
    idx = index.get_index()
    assert idx.size == 0


def test_embedding_batches_are_bounded(monkeypatch) -> None:
    """The OOM was one 3429-text forward pass; batch size must cap every call."""
    monkeypatch.setattr(embeddings, "_use_openai", lambda: False)
    monkeypatch.setattr(embeddings, "_embed_batch", lambda texts: [[0.0]] * len(texts))
    os.environ["EMBEDDING_BATCH_SIZE"] = "8"
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
        os.environ.pop("EMBEDDING_BATCH_SIZE", None)
        _reset_settings()


def test_api_batches_are_larger_than_local_ones() -> None:
    """Opposite limits: the local model is capped by memory, the hosted one by round trips."""
    s = get_settings()
    assert s.embedding_api_batch_size > s.embedding_batch_size


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
