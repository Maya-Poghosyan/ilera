# Scoped policy retrieval

Ilera keeps one hosted policy database. A document can be associated with multiple
programs without duplicating its text or embeddings. Every search now requires a
`RetrievalScope(program, state, as_of)` supplied by application code.

## Authored metadata

Each `data/knowledge/manifest.json` entry (or `reference.rag_sources.meta` row)
contains:

| Field | Meaning |
| --- | --- |
| `applicable_programs` | Program keys permitted to retrieve this source; includes its primary `program` |
| `jurisdictions` | `US` for federal sources, or explicit state/territory abbreviations such as `CA` |
| `effective_from` | Inclusive policy applicability start, ISO date; null means unknown |
| `effective_to` | Exclusive policy applicability end, ISO date; null means no known end |
| `authority_level` | Existing curated source-authority description |
| `version` | Curated revision/edition identifier; empty means unknown |

All 35 current documents have explicit California or federal jurisdiction based
on their existing issuing-agency metadata. Effective dates and edition identifiers
are not inferred from filenames or publication dates. They remain unverified until
curated. A document with unknown dates is eligible for retrieval but returned with
`date_status: unverified`; this is not confirmation it is current. A document
without jurisdiction metadata is excluded. Dates filter known applicability
windows; they do not resolve contradictions or supersession automatically.

A federal document shared between specialists can list, for example,
`applicable_programs: ["tax", "ihss"]` while retaining primary `program: "tax"`.
Assign these associations explicitly after verifying relevance. The returned
`program` identifies the source's primary collection; `policy.applicable_programs`
identifies all permitted specialist scopes. `US` sources are included for every
state within their assigned programs; a source describing federal rules does not
establish state implementation.

Use unique document IDs for different editions. Do not reuse a single document ID
for two state-specific sources or overwrite a historical edition needed for past
dates. Within an edition that discusses several policy periods, document-level
windows cannot replace careful interpretation of the passages.

## Storage and searches

`rag_chunks` continues to hold the existing vectors and text. The additive
`rag_document_scopes` catalog stores one metadata row per document with GIN indexes
on program associations and jurisdictions. Scope edits update this catalog without
changing embedding fingerprints or re-embedding documents.

Postgres materializes the eligible program/jurisdiction/date subset before exact
vector ranking. This prevents a global approximate index from underfilling results
after selective filters. This favors correct scoped top-k for the current corpus.
It does not add partitioned vector indexes. Benchmark recall and latency with
representative larger corpora before introducing partitions or iterative ANN scans.
The memory backend applies the same scope rules before ranking.

## Application boundaries

Specialists derive location from explicit intake answers or canonical facts marked
known. Serialized model defaults such as `CA` do not establish location. Recipient
residence scopes recipient programs; caregiver residence scopes PFL and tax
research. Unknown/conflicting location permits federal documents only. Residence
is a retrieval context, not proof of state employment/leave eligibility; cross-state
employment needs its own facts and future routing. Calls use the current UTC policy
date unless an explicit `as_of` is supplied. Tax-year-specific research should
provide the relevant date explicitly; current-date retrieval does not establish
historical tax-year applicability.

The research CLI supports `--state CA --as-of 2026-10-14` and records both in its
output. The default CLI state remains CA for current Ilera research. The specialist
tool's scope is fixed before the model runs; its query cannot change that scope.
Retrieval errors raise instead of advising the model to rely on general knowledge.
Zero matching passages are identified as a coverage gap, not a negative verdict.

`POST /api/rag/search` now requires `program` and `state` in addition to `query`;
`as_of` is optional and defaults to the current UTC date. Example request body:

```json
{"query":"citizenship requirements","program":"medical","state":"CA","as_of":"2026-10-14","k":5}
```

## Rollout

1. Before deploying the new API and Functions code, run the metadata migration
   using the backend's existing configured credentials:
   `python -m app.rag.ingest --metadata-only`.
2. Confirm catalog rows/jurisdictions match the authored source metadata. Existing
   DB metadata is authoritative; newly added scope fields are backfilled from the
   bundled manifest only when absent for a known document.
   For subsequent curation, update `reference.rag_sources.meta` when using the
   DB-backed corpus, then rerun metadata sync. Editing the bundled manifest alone
   will not override existing explicit DB scope fields.
3. Deploy the API and eligibility Functions together. Old code ignores the
   additive catalog, so migrating first is compatible with the current deployment.
4. Run scoped research for CA and another state. California-only documents must
   not appear for the other state; applicable federal sources should remain.

Normal incremental ingest also creates/updates the catalog. The metadata-only
migration changes no source text or embeddings and does not delete any policy
chunks. Do not use `--rebuild` for this rollout. A configured hosted index with a
missing catalog fails explicitly and cannot silently switch to local documents.
This checkout implements the migration and retrieval changes; deployment and
persistent Azure catalog migration are separate operations.

## Validation

`test_rag_scope.py` covers wrong-state/program exclusion, inclusive starts,
exclusive ends, shared federal sources, missing jurisdiction, unknown dates,
serialized defaults, conflicting facts, required API scope, and tool failures.
`test_rag_scope_postgres.py` repeats the critical search checks on real pgvector
when `TEST_RAG_DATABASE_URL` is provided, using only session-local temporary tables.
It confirms metadata updates leave vectors untouched.
