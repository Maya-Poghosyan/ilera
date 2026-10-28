"""Real pgvector tests using session-local tables; no persistent data is changed."""
import os
from contextlib import contextmanager
from datetime import date

import pytest

from app.rag import index
from app.rag.scope import PolicyMetadata, RetrievalScope

DSN = os.environ.get("TEST_RAG_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_RAG_DATABASE_URL not set")


def test_real_postgres_scoped_search_and_metadata_updates(monkeypatch):
    import psycopg
    try:
        connection = psycopg.connect(DSN)
    except psycopg.Error:
        pytest.fail("Test database connection failed; check connectivity/authentication.", pytrace=False)
    with connection as conn:
        conn.execute("""CREATE TEMP TABLE rag_chunks (
            id text PRIMARY KEY, program text, source text, title text, source_url text,
            document_id text, page text, doc_hash text, text text, embedding vector(3))""")
        conn.execute("""CREATE TEMP TABLE rag_document_scopes (
            document_id text PRIMARY KEY, applicable_programs text[] NOT NULL,
            jurisdictions text[] NOT NULL, effective_from date, effective_to date,
            authority_level text NOT NULL DEFAULT '', version text NOT NULL DEFAULT '')""")
        class Pool:
            @contextmanager
            def connection(self):
                yield conn
        idx = index.PgVectorIndex.__new__(index.PgVectorIndex)
        idx._pool = Pool()
        idx._size = 7
        idx._dim = 3
        idx._create_scope_schema(conn)
        policies = {
            "CA": PolicyMetadata(("medical",), ("CA",), date(2026, 1, 1)),
            "NY": PolicyMetadata(("medical",), ("NY",)),
            "federal": PolicyMetadata(("tax", "medical"), ("US",)),
            "expired": PolicyMetadata(("medical",), ("CA",), None, date(2026, 10, 14)),
            "future": PolicyMetadata(("medical",), ("CA",), date(2026, 10, 15)),
            "other-program": PolicyMetadata(("tax",), ("CA",)),
            "unknown-state": PolicyMetadata(("medical",), ()),
        }
        for key, policy in policies.items():
            doc = index.Document(key, policy.applicable_programs[0], key, policy=policy)
            idx._write_scope(conn, doc)
            conn.execute("""INSERT INTO rag_chunks (id, program, source, title, source_url,
                document_id, page, doc_hash, text, embedding)
                VALUES (%s, %s, %s, %s, '', %s, '1', 'unchanged', %s, %s::vector)""",
                (key, doc.program, key, key, key, key, "[0.9,0.1,0]" if key == "CA" else "[1,0,0]"))
        conn.execute("INSERT INTO rag_chunks (id, document_id, text, embedding) VALUES ('orphan','orphan','orphan','[1,0,0]')")
        monkeypatch.setattr(index, "embed_one", lambda _: [1, 0, 0])
        ca = RetrievalScope("medical", "CA", date(2026, 10, 14))
        hits = idx.search("policy", k=5, scope=ca)
        assert {h.document_id for h in hits} == {"CA", "federal"}
        assert hits[0].document_id == "federal"
        assert hits[1].policy["effective_from"] == "2026-01-01"
        assert hits[0].policy["date_status"] == "unverified"
        assert {h.document_id for h in idx.search("policy", scope=RetrievalScope("medical", "NY", ca.as_of))} == {"NY", "federal"}
        assert {h.document_id for h in idx.search("policy", scope=RetrievalScope("medical", None, ca.as_of))} == {"federal"}
        assert "future" in {h.document_id for h in idx.search("policy", k=10, scope=RetrievalScope("medical", "CA", date(2026, 10, 15)))}
        before = conn.execute("SELECT id, doc_hash, embedding::text FROM rag_chunks ORDER BY id").fetchall()
        idx._write_scope(conn, index.Document("CA", "medical", "CA", policy=PolicyMetadata(("medical",), ("NY",))))
        assert {h.document_id for h in idx.search("policy", scope=ca)} == {"federal"}
        after = conn.execute("SELECT id, doc_hash, embedding::text FROM rag_chunks ORDER BY id").fetchall()
        assert before == after
