# Ilera — Agentic assistance for caregivers

**🏆 1st place — Harvard Health Systems Innovation Lab Hackathon**

Ilera helps unpaid caregivers discover, optimize, and apply for state and federal benefits
(IHSS, Medi-Cal, Paid Family Leave, VA, and more) using a multi-agent system grounded in
official program documentation. After eligibility is determined, caregivers get a full
dashboard: care calendar, timekeeping, journal, renewals, and auto-filled government PDFs.

## What it does

1. **Intake** — a short, schema-driven wizard builds a `CaseProfile` from the caregiver's answers.
2. **Eligibility** — a routing agent fans out to program-specialist agents (IHSS, Medi-Cal, PFL, VA, …), each grounded in its own RAG corpus. Results come back ranked by match level with a plain-language strategy.
3. **Applications** — the backend resolves the `CaseProfile` against PDF field maps, auto-fills what it can, and asks only for what's missing. The caregiver downloads a completed, stitched PDF.
4. **Dashboard** — care calendar with Poke-detected events, timekeeping, care journal, renewal tracking, and SMS reminders.

## Architecture

```
Next.js frontend  ──REST──▶  FastAPI backend
  intake wizard                 accounts, CaseProfile, records (Postgres / in-memory)
  eligibility cards               │
  applications flow               ├─ Routing Agent ──▶ specialist agents (IHSS, Medi-Cal, PFL, VA, …)
  dashboard                       │       pydantic-ai, each grounded in program-scoped RAG
                                  ├─ RAG over program docs (pgvector / in-memory fallback)
                                  └─ form fill + stitch (pypdf / fillpdf)
                          integrations: Poke (SMS reminders + inbox scanning)
```

The **`CaseProfile`** is the shared spine: every agent reads from it and writes findings back to it.

## Repo layout

```
frontend/   Next.js + TypeScript + Tailwind + shadcn/ui
backend/    FastAPI app
  app/
    agents/     routing coordinator + specialist agents
    rag/        embeddings + vector index (pgvector, in-memory fallback)
    forms/      PDF field-map fill + stitch
    models.py   CaseProfile + EligibilityResult + supporting types
    main.py     API endpoints
  data/
    program_docs/   official program text for RAG
    form_schemas/   PDF field → CaseProfile path maps
```

## Quickstart

Everything boots **without any API keys** — RAG falls back to a local embedding model and
the data stores fall back to in-memory. Add keys to go production-grade.

### Backend

Requires **Python ≥ 3.11**.

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # optional: add Postgres / LLM / Poke keys
uvicorn app.main:app --reload --port 8000
```

### RAG index

Embedding the corpus is a one-time offline step — the server attaches to an existing index.

```bash
cd backend
DATABASE_URL=postgresql://... python -m app.rag.ingest
```

The ingest is incremental: each document is stored with a fingerprint of its text, chunking
parameters, and embedding model, so a re-run only re-embeds what changed. `--rebuild` forces
a full re-embed.

Merging a change under `backend/data/knowledge/` is enough in practice —
`.github/workflows/rag-ingest.yml` runs the sync against the production store on every push
to `main`. It needs `DATABASE_URL` and `OPENAI_API_KEY` as repository secrets, an
`OPENAI_BASE_URL` variable, and the database to accept connections from GitHub's runners.

Without `DATABASE_URL`, the index falls back to memory (no fingerprints, so every sync is a
full rebuild). If you deploy before ingesting, retrieval returns nothing — `/health` reports
`rag_chunks: 0`.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local     # set API_URL (server-side only)
npm run dev                           # http://localhost:3000
```

Open http://localhost:3000 → **Get started** → intake → eligibility results → dashboard.

## Security model

The browser only ever calls its own origin. `src/app/api/[...path]/route.ts` proxies
`/api/*` to `API_URL`, which is a runtime server variable — never a `NEXT_PUBLIC_*` value
frozen into the bundle. Modules that import it also import `server-only`, so accidentally
using it in a client component fails the build.

Session tokens follow the same rule: `/api/auth/{signup,login}` set an httpOnly cookie; the
proxy converts it back to an `Authorization` header on every backend call. Client code never
holds a token, so an XSS bug has nothing to steal.

## Resilience

1. **Reads retry themselves.** `lib/api.ts` retries GET requests twice (400ms, then 1.2s) on
   502/503/504 or network failure — enough to ride out a container restart. Writes are never
   replayed. A read that still fails renders a `LoadFailure` with a retry button.
2. **Intake survives outages.** Answers are written to localStorage on every step, so a
   network failure mid-wizard costs a caregiver a retry click, not their answers.

## Deploying

`.github/workflows/deploy.yml` deploys on every push to `main` that touches `backend/**` or
`frontend/**`, sending each to its own container app on Azure. Images are built by ACR and
tagged with the commit SHA. After each update the workflow polls `/healthz` (and `/readyz`
for the API) for ten minutes, so a revision that fails to come up shows as a failed CI run.

One-time setup — repository variables:

| Variable | Value |
|---|---|
| `AZURE_RESOURCE_GROUP` | `Ilera` |
| `AZURE_REGISTRY` | ACR name (no `.azurecr.io`) |
| `API_APP` / `WEB_APP` | the two container app names |
| `API_HOST` / `WEB_HOST` | `api.ileracare.app` / `ileracare.app` |

Federated credentials (no stored passwords):

```bash
RG=Ilera; SUB=$(az account show --query id -o tsv); REPO=Maya-Poghosyan/ilera
app=$(az ad app create --display-name ilera-deploy --query appId -o tsv)
az ad sp create --id "$app"
az role assignment create --assignee "$app" --role Contributor \
  --scope "/subscriptions/$SUB/resourceGroups/$RG"
az ad app federated-credential create --id "$app" --parameters "{
  \"name\": \"main\", \"issuer\": \"https://token.actions.githubusercontent.com\",
  \"subject\": \"repo:$REPO:ref:refs/heads/main\", \"audiences\": [\"api://AzureADTokenExchange\"]}"
echo "AZURE_CLIENT_ID=$app  AZURE_TENANT_ID=$(az account show --query tenantId -o tsv)  AZURE_SUBSCRIPTION_ID=$SUB"
```

Save those three as repository **secrets**.

## Case ownership

Intake is anonymous — a case exists before an account does. `cases.owner_user_id` is
nullable. An unowned case is reachable by whoever holds its ID. Signing up or logging in
claims it permanently; a stranger who guesses a case ID can neither read it nor attach it to
their account. Every case-scoped route enforces this via `app/access.py`, responding 404
rather than 403 to avoid confirming the case exists. Unclaimed cases are deleted after
`UNCLAIMED_CASE_TTL_DAYS`.

## API reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | status + Postgres/LLM config + RAG chunk count |
| GET | `/healthz` | liveness (no dependencies touched) |
| GET | `/readyz` | readiness — 503 while Postgres is unreachable |
| POST | `/api/intake` | create or update a CaseProfile (no account required) |
| POST | `/api/eligibility/{id}` | run routing + specialists, return ranked results |
| GET | `/api/eligibility/{id}` | poll for results |
| GET | `/api/case/{id}` | fetch a CaseProfile (owner only) |
| PATCH | `/api/auth/me` | update account name or claim an anonymous case |
| POST | `/api/rag/search` | semantic search over program docs |
| GET | `/api/forms/{form_id}/{case_id}` | resolved PDF fields + what's still missing |
| GET | `/api/applications/{case_id}` | list programs with eligibility + form status |
| POST | `/api/applications/{case_id}/{program}/start` | auto-fill and return missing questions |
| POST | `/api/applications/{case_id}/{program}/preview` | generate a stitched PDF preview |
| POST | `/api/applications/{case_id}/{program}/submit` | finalize and download PDF |
| GET | `/api/reminders` | list reminders |
| POST | `/api/reminders` | create a reminder |
| PATCH | `/api/reminders/{id}` | update a reminder |
| DELETE | `/api/reminders/{id}` | delete a reminder |
| POST | `/api/reminders/{id}/run-now` | fire a reminder immediately via Poke |

## Wiring real services

- **Postgres:** set `DATABASE_URL` — all stores persist (`users`, `cases`, `reminders`,
  `timekeeping`, `journal`, `renewals`, `applications`, `preferences`, `suggested_events`)
  and the same database serves the pgvector RAG index. Without it, every store falls back to
  an in-process dict.
- **LLM:** set `OPENAI_API_KEY` (OpenAI or Azure OpenAI via `OPENAI_BASE_URL`).
- **Poke:** set `POKE_API_KEY` — SMS reminders and inbox scanning activate. All Poke paths
  gracefully no-op when the key is absent.
- **Forms:** drop fillable government PDFs into `backend/data/` and fill out the corresponding
  field-map JSONs in `backend/data/form_schemas/`.
