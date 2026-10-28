"""Policy boundaries must hold even when excluded passages are the closest vectors."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.models import CaseProfile
from app.rag import index
from app.rag.scope import PolicyMetadata, RetrievalScope, profile_scope

AS_OF = date(2026, 10, 14)


@pytest.fixture(autouse=True)
def offline_embedding_identity(monkeypatch):
    # Fingerprint tests exercise invalidation, not model downloads/API access.
    monkeypatch.setattr(index, "embedding_provider", lambda: "test")
    monkeypatch.setattr(index, "embedding_id", lambda: "test-model")


def metadata(programs=("medical",), jurisdictions=("CA",), start=None, end=None):
    return PolicyMetadata.from_dict({"applicable_programs": list(programs),
                                    "jurisdictions": list(jurisdictions),
                                    "effective_from": start, "effective_to": end}, programs[0])


def test_scope_filters_program_state_and_effective_interval_before_top_k(monkeypatch):
    monkeypatch.setattr(index, "embed_one", lambda _: [1.0, 0.0])
    idx = index.RagIndex()
    policies = {
        "wrong-state": metadata(jurisdictions=("NY",)),
        "wrong-program": metadata(programs=("tax",)),
        "expired": metadata(end="2026-10-14"),
        "future": metadata(start="2026-10-15"),
        "unclassified": metadata(jurisdictions=()),
        "state": metadata(start="2026-10-14"),
        "federal-shared": metadata(programs=("tax", "medical"), jurisdictions=("US",)),
    }
    idx._chunks = [index.Chunk(id=key, program=policy.applicable_programs[0],
                               text=key, source=key, document_id=key, vector=[1.0, 0.0], policy=policy)
                   for key, policy in policies.items()]
    hits = idx.search("test", k=2, scope=RetrievalScope("medical", "CA", AS_OF))
    assert {h.document_id for h in hits} == {"state", "federal-shared"}
    assert next(h for h in hits if h.document_id == "federal-shared").policy["date_status"] == "unverified"
    hits = idx.search("test", scope=RetrievalScope("medical", "NY", AS_OF))
    assert {h.document_id for h in hits} == {"wrong-state", "federal-shared"}
    hits = idx.search("test", scope=RetrievalScope("medical", None, AS_OF))
    assert {h.document_id for h in hits} == {"federal-shared"}


def test_scope_validation_and_date_boundaries():
    assert RetrievalScope("tax", "ny", AS_OF).state == "NY"
    for bad in ("US", "ZZ", "", "California"):
        with pytest.raises(ValueError):
            RetrievalScope("tax", bad, AS_OF)
    with pytest.raises(ValueError):
        metadata(start="2026-10-14", end="2026-10-14")
    with pytest.raises(ValueError):
        metadata(jurisdictions=("ZZ",))
    with pytest.raises(ValueError):
        PolicyMetadata.from_dict({"jurisdictions": "CA"}, "medical")
    with pytest.raises(ValueError):
        PolicyMetadata.from_dict({"applicable_programs": ["tax"]}, "medical")


def test_profile_location_uses_evidence_not_serialized_defaults():
    profile = CaseProfile.model_validate_json(CaseProfile(id="test").model_dump_json())
    assert profile_scope(profile, "medical").state is None
    profile.answers = {"caregiver.address.state": "NY", "recipient.address.state": "TX",
                       "caregiver.coresidence": "No"}
    assert profile_scope(profile, "medical").state == "TX"
    assert profile_scope(profile, "pfl").state == "NY"
    profile.answers["caregiver.coresidence"] = "Yes"
    assert profile_scope(profile, "ihss").state == "NY"
    profile.fact_metadata["care_recipient.state"] = SimpleNamespace(availability="conflicting")
    assert profile_scope(profile, "ihss").state is None
    profile.fact_metadata["care_recipient.state"] = SimpleNamespace(availability="known")
    profile.care_recipient.state = "IL"
    assert profile_scope(profile, "medical").state == "IL"


def test_metadata_changes_do_not_require_reembedding():
    a = index.Document("shared", "tax", "Same federal source", policy=metadata(programs=("tax",), jurisdictions=("US",)))
    b = index.Document("shared", "tax", "Same federal source", policy=metadata(programs=("tax", "medical"), jurisdictions=("US",), start="2026-01-01"))
    assert a.fingerprint() == b.fingerprint()
    assert b.chunks()[0].policy == b.policy


def test_bundled_corpus_has_explicit_jurisdiction_and_authority():
    from app.rag.source_store import iter_source_files
    docs = list(iter_source_files())
    assert len(docs) >= 35
    assert all(d.policy.jurisdictions and d.policy.authority_level for d in docs)
    assert next(d for d in docs if d.document_id == "ACWDL-25-14").policy.jurisdictions == ("CA",)
    assert next(d for d in docs if d.document_id == "CMS-MSP-CHAPTER-1").policy.jurisdictions == ("US",)


def test_postgres_search_binds_scope_and_materializes_eligible_subset(monkeypatch):
    from contextlib import contextmanager
    captured = []
    class Connection:
        def execute(self, sql, params):
            captured.append((sql, params))
            return SimpleNamespace(fetchall=lambda: [])
    class Pool:
        @contextmanager
        def connection(self):
            yield Connection()
    idx = index.PgVectorIndex.__new__(index.PgVectorIndex)
    idx._size = 1
    idx._pool = Pool()
    monkeypatch.setattr(index, "embed_one", lambda _: [1, 0])
    idx.search("test", scope=RetrievalScope("medical", "NY", AS_OF))
    sql, params = captured[0]
    assert "AS MATERIALIZED" in sql
    assert "JOIN rag_document_scopes" in sql
    assert params[:4] == [["medical"], ["US", "NY"], AS_OF, AS_OF]
    assert "NY" not in sql


def test_metadata_only_sync_never_embeds_and_updates_unchanged_docs(monkeypatch):
    from contextlib import contextmanager
    class Pool:
        @contextmanager
        def connection(self):
            yield object()
    idx = index.PgVectorIndex.__new__(index.PgVectorIndex)
    idx._pool = Pool()
    writes = []
    monkeypatch.setattr(idx, "_create_scope_schema", lambda conn: None)
    monkeypatch.setattr(idx, "_write_scope", lambda conn, doc: writes.append(doc.policy))
    monkeypatch.setattr(index, "iter_documents", lambda: iter([index.Document("D", "tax", "text", policy=metadata(programs=("tax",), jurisdictions=("US",)))]))
    monkeypatch.setattr(index, "embed", lambda _: pytest.fail("Metadata migration must not embed"))
    assert idx.sync_metadata() == 1
    assert len(writes) == 1


def test_specialist_tool_enforces_application_scope_and_failure(monkeypatch):
    import asyncio
    from durable.tools.rag_tool import make_rag_tool
    scope = RetrievalScope("medical", "NY", AS_OF)
    seen = []
    def search(query, k, *, scope):
        seen.append(scope)
        return []
    monkeypatch.setattr(index, "get_index", lambda: SimpleNamespace(search=search))
    result = asyncio.run(make_rag_tool("medical", scope)("citizenship"))
    assert seen == [scope]
    assert "coverage gap" in result
    with pytest.raises(ValueError):
        make_rag_tool("tax", scope)
    monkeypatch.setattr(index, "get_index", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(make_rag_tool("medical", scope)("citizenship"))


def test_rag_api_requires_explicit_scope():
    from app.routes.rag import RagQuery
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RagQuery(query="citizenship")
    with pytest.raises(ValidationError):
        RagQuery(query="citizenship", program="medical", state="ZZ")
    with pytest.raises(ValidationError):
        RagQuery(query="citizenship", program="medical", state="CA", k=100)
    query = RagQuery(query="citizenship", program="medical", state="CA", as_of="2026-10-14")
    assert query.as_of == AS_OF


def test_hosted_scope_failure_cannot_fall_back_to_local(monkeypatch):
    closed = []
    class BrokenIndex:
        def __init__(self, dsn):
            self._pool = SimpleNamespace(close=lambda: closed.append(True))
        def ensure(self):
            raise RuntimeError("scope catalog absent")
    monkeypatch.setattr(index, "get_settings", lambda: SimpleNamespace(has_postgres=True, database_url="test"))
    monkeypatch.setattr(index, "PgVectorIndex", BrokenIndex)
    with pytest.raises(RuntimeError, match="catalog absent"):
        index._make_index(force=False)
    assert closed == [True]


def test_source_metadata_backfill_preserves_explicit_db_scope(monkeypatch):
    from contextlib import contextmanager
    from app.rag import source_store
    rows = [
        ("old", "medical", "Old", "", "text", {"authority_level": "manual"}),
        ("new", "medical", "New", "", "text", {"jurisdictions": ["NY"]}),
        ("unclassified", "medical", "Unknown", "", "text", {"jurisdictions": []}),
    ]
    @contextmanager
    def connection():
        yield SimpleNamespace(execute=lambda _: SimpleNamespace(fetchall=lambda: rows))
    monkeypatch.setattr(source_store, "_db_has_sources", lambda: True)
    monkeypatch.setattr(source_store.db, "connection", connection)
    monkeypatch.setattr(source_store, "_manifest_entries", lambda: {
        "old": {"jurisdictions": ["CA"], "authority_level": "letter"},
        "new": {"jurisdictions": ["CA"]},
        "unclassified": {"jurisdictions": ["CA"]},
    })
    docs = list(source_store.iter_sources())
    assert docs[0].policy.jurisdictions == ("CA",)
    assert docs[0].policy.authority_level == "manual"
    assert docs[1].policy.jurisdictions == ("NY",)
    assert docs[2].policy.jurisdictions == ()
