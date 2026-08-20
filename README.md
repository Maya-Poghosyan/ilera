# Ilera — Agentic assistance for caregivers

Ilera helps unpaid caregivers discover, optimize, and apply for state/federal benefits
(IHSS, Medi-Cal, Paid Family Leave, VA, …) using a multi-agent system grounded in
official program documentation, then supports them with a care calendar, timekeeping,
and a document store.

Built for the UC Berkeley AI Hackathon. Tracks: **Band** (multi-agent), **Poke**
(agentic reminders), **Devin** (built with Devin).

## Architecture

```
Next.js frontend  ──REST──▶  FastAPI backend
  intake wizard                 accounts, CaseProfile, records (Postgres / in-memory)
  eligibility cards               │
  dashboard                       ├─ Routing Agent ──▶ specialist agents (IHSS, Medi-Cal, PFL, VA)
                                  │       coordinate in a shared agent space (Band)
                                  ├─ RAG over program docs (pgvector)
                                  └─ form fill + stitch (pypdf / fillpdf)
                          integrations: Poke (SMS/email)
```

The **`CaseProfile`** is the shared spine: every agent reads and writes it.

## Repo layout

```
frontend/   Next.js 14 + TS + Tailwind + shadcn/ui
backend/    FastAPI app
  app/
    agents/     routing + specialists + Band shared space
    rag/        embeddings + vector index (pgvector, in-memory fallback)
    forms/      PDF field-map fill + stitch
    models.py   CaseProfile + EligibilityResult
    main.py     API endpoints
  data/
    program_docs/   official program text for RAG (sample placeholders included)
    form_schemas/   PDF field -> CaseProfile path maps
```

## Quickstart

Everything boots **without any API keys** — RAG falls back to a local embedding and
the CaseProfile store falls back to in-memory. Add keys to go production-grade.

### Backend

Requires **Python ≥ 3.11** (`band-sdk` in `requirements.txt` does not support 3.10).

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate   # or any python ≥3.11
pip install -r requirements.txt
cp .env.example .env        # optional: add Postgres / LLM / Band / Poke keys
uvicorn app.main:app --reload --port 8000
```

### RAG index (offline)

Embedding the ~3.4k-chunk corpus costs hundreds of MB and several minutes, so this is the
only place it happens — the server never builds an index, it attaches to one.

```bash
cd backend
DATABASE_URL=postgresql://... python -m app.rag.ingest
```

The ingest is incremental and safe to re-run: every document is stored with a fingerprint of
its text, the chunking parameters and the embedding model, so a run re-embeds only the
documents that changed and drops rows for documents removed from the manifest. An unchanged
corpus costs one query. `--rebuild` forces a full re-embed.

Because of that, merging a change under `backend/data/knowledge/` is all that's needed in
practice: `.github/workflows/rag-ingest.yml` runs the sync against the production store on
push to `main`. It needs the `DATABASE_URL` and `OPENAI_API_KEY` repository secrets, an
`OPENAI_BASE_URL` repository variable, and the database to accept connections from GitHub's
runners.

With `DATABASE_URL` set (Postgres + `pgvector`) the chunk text and the KNN both live in the
database; without it, the index falls back to memory (which tracks no fingerprints, so there a
sync is a full rebuild). If you deploy before ingesting, the server logs an error and retrieval
returns nothing — `/health` reports `rag_chunks: 0`.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local     # API_URL, server-side only
npm run dev                 # http://localhost:3000
```

Then open http://localhost:3000 → **Start intake** → eligibility results → dashboard.

## Talking to the API

The browser only ever calls the frontend's own origin. `src/app/api/[...path]/route.ts` forwards
`/api/*` to `API_URL`, so the backend's address is a runtime server variable rather than a
`NEXT_PUBLIC_*` value frozen into the bundle at build time — one image runs against any backend,
and a missing value can't silently turn every request into a same-origin 404. Modules holding it
import `server-only`, so leaking it into a client component fails the build instead of shipping.

The session token follows the same rule: `/api/auth/{signup,login}` keep it server-side and hand
the browser an httpOnly cookie, which the proxy turns back into an `Authorization` header. Client
code never holds a token, so an XSS bug has nothing to steal. Cross-origin requests disappear
with it, making `CORS_ORIGINS` unnecessary for the app itself.

## Staying up (and failing gracefully)

An outage should be a delay, not a dead end. Two things arranged in order of how much they help:

1. **Reads retry themselves.** `lib/api.ts` retries a GET twice (400ms, 1.2s) when the API answers
   502/503/504 or is unreachable, which covers the seconds a restart takes. Writes are never
   replayed — a retried POST could file a second application. A read that still fails renders
   `LoadFailure` with a Try again button.
2. **Intake survives it.** Answers are drafted to localStorage on every step, so an outage
   mid-wizard costs a caregiver a retry, not their answers.

The container apps use Azure's default TCP check on the ingress port. HTTP probes on `/healthz`
and `/readyz` were tried and reverted: a probe that misfires holds traffic off a revision whose
process is fine, which is a worse failure than the one it prevents.

## Deploying

`.github/workflows/deploy.yml` deploys on every push to `main` that touches `backend/**` or
`frontend/**` — the backend to one container app, the frontend to the other, never the reverse.
That mix-up is easy by hand (`az containerapp up` builds whatever directory you're standing in)
and is what put the frontend image into `ilera-api`. Images are built by ACR itself, so no
registry password exists in CI, and are tagged with the commit sha rather than `latest`, so a
revision names the code it runs. After each update the workflow polls the app's public
`/healthz` (plus `/readyz` for the API) for ten minutes, so a deploy that doesn't come up shows as
a failed run rather than something you discover in a browser. It deliberately does *not* roll back:
the previous image isn't known to be good, and reverting to a broken one only lengthens the outage.

One-time setup. Repository variables (Settings → Secrets and variables → Actions → Variables):

| Variable | Value |
| --- | --- |
| `AZURE_RESOURCE_GROUP` | `Ilera` |
| `AZURE_REGISTRY` | `caff3fa0d6e7acr` (name only, no `.azurecr.io`) |
| `API_APP` / `WEB_APP` | the two container app names, e.g. `ilera-api` / `ilera-web` |
| `API_HOST` / `WEB_HOST` | `api.ileracare.app` / `ileracare.app` |

Then federated credentials, so GitHub authenticates with a short-lived token and no password is
stored anywhere:

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

Save those three as repository **secrets**. The subject is pinned to `refs/heads/main`, so a
workflow run from a fork or a branch cannot obtain the credential; add a second federated
credential with `subject: repo:$REPO:environment:production` if you later gate deploys on a
GitHub Environment. `workflow_dispatch` runs on `main` still work, and take an `api`/`web`/`both`
choice for redeploying without a code change.

## Case ownership

Intake is anonymous — a case exists before its caregiver has an account — so `cases.owner_user_id`
is nullable, with a foreign key to `users`. An unowned case is reachable by whoever holds its id;
signing up (or logging in) claims it, and a claim is permanent, so a stranger who guesses a case
id can neither read it nor attach it to their own account. Every case-scoped route enforces this
(`app/access.py`) and answers 404 rather than 403, which would confirm the case exists. Cases that
are never claimed are deleted after `UNCLAIMED_CASE_TTL_DAYS`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | status + whether Postgres/LLM are configured + RAG chunk count |
| GET | `/healthz` | liveness: the process is up (no dependencies touched) |
| GET | `/readyz` | readiness: 503 while Postgres is configured but unreachable |
| POST | `/api/intake` | create/update a CaseProfile (no account needed) |
| PATCH | `/api/auth/me` | rename the account, and/or claim the case from an anonymous intake |
| GET | `/api/case/{id}` | fetch a CaseProfile (owner only, once claimed) |
| POST | `/api/eligibility/{id}` | run routing + specialists, return ranked results |
| POST | `/api/rag/search` | semantic search over program docs |
| GET | `/api/forms/{program}/{id}` | resolved PDF fields + what's still missing |
| GET | `/api/reminders` | list all scheduled reminders |
| POST | `/api/reminders` | create a new reminder |
| GET | `/api/reminders/templates` | built-in reminder templates (care-log, IHSS, Medi-Cal, PFL, appointment) |
| GET | `/api/reminders/{id}` | get a single reminder |
| PATCH | `/api/reminders/{id}` | update a reminder |
| DELETE | `/api/reminders/{id}` | delete a reminder |
| POST | `/api/reminders/{id}/run-now` | immediately fire a reminder via Poke |
| POST | `/api/reminders/send` | send an ad-hoc message via Poke |

## Poke integration

Ilera uses [Poke](https://poke.com) to deliver caregiver reminders into the user's
chat (iMessage, WhatsApp, Telegram, RCS). Set `POKE_API_KEY` in `backend/.env`.

**Features:**
- Schedule recurring (daily/weekly) or one-off reminders via the dashboard Reminders page.
- Built-in templates: daily care-log check-in, IHSS timesheet, Medi-Cal renewal, PFL weekly cert, appointment.
- One-click "Enable Daily Care Log" that sends an end-of-day prompt asking about hours, meals, meds, mood.
- Lightweight asyncio scheduler fires due reminders every 30 seconds.
- All endpoints and the scheduler gracefully no-op if `POKE_API_KEY` is not set.

## Next steps (wiring real services)

- **Postgres:** set `DATABASE_URL` and every store persists — `users`, `cases`, `band_rooms`,
  `reminders`, `timekeeping`, `journal`, `renewals`, `applications`, `preferences`,
  `suggested_events` (all created on first use) — and the same database serves the pgvector
  RAG index. Without it, each store falls back to an in-process dict.
- **LLM:** set `OPENAI_API_KEY` (OpenAI or an Azure OpenAI endpoint via `OPENAI_BASE_URL`);
  replace heuristic `assess()` bodies in `app/agents/specialists.py` with grounded LLM calls.
- **Band:** wired as a true multi-agent system — **each program group is its own Band agent**
  (IHSS, Medi-Cal, Medicare, PFL, VA, Tax), grounded only in its program's docs, plus a
  routing coordinator. Create a Remote Agent on app.band.ai per group, copy
  `backend/band_agents.example.json` → `backend/band_agents.json`, and fill in each agent's
  UUID + API key. Then `pip install -r requirements-band.txt` and run the worker:
  `python -m app.integrations.band` (it launches every configured agent). Specialists expose
  program-scoped `assesseligibility` + `lookupprogramdocs` tools; the router exposes the
  cross-program `assesseligibility` + `searchprogramdocs`. `app/agents/band_space.py`
  still handles in-process coordination for the synchronous HTTP flow.
- **Poke:** `POKE_API_KEY` is now wired — reminders are delivered. See the Poke section above.
- **Forms:** drop fillable government PDFs into `backend/data/` and fill out the field-map JSONs.
```
