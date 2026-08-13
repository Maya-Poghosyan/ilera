# Ilera — Agentic assistance for caregivers

Ilera helps unpaid caregivers discover, optimize, and apply for state/federal benefits
(IHSS, Medi-Cal, Paid Family Leave, VA, …) using a multi-agent system grounded in
official program documentation, then supports them with a care calendar, timekeeping,
and a document store.

Built for the UC Berkeley AI Hackathon. Tracks: **Band** (multi-agent), **Redis**
(RAG + agent memory + document store), **Poke** (agentic reminders), **Devin**
(built with Devin).

## Architecture

```
Next.js frontend  ──REST──▶  FastAPI backend
  intake wizard                 accounts + CaseProfile (Postgres / in-memory)
  eligibility cards               │
  dashboard                       ├─ Routing Agent ──▶ specialist agents (IHSS, Medi-Cal, PFL, VA)
                                  │       coordinate in a shared agent space (Band)
                                  ├─ RAG over program docs (RedisVL)
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
    rag/        embeddings + vector index (pgvector, RedisVL, in-memory fallback)
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
cp .env.example .env        # optional: add Redis / Postgres / LLM / Band / Poke keys
uvicorn app.main:app --reload --port 8000
```

### RAG index (offline)

Embedding the ~3.4k-chunk corpus costs hundreds of MB and several minutes, so this is the
only place it happens — the server never builds an index, it attaches to one.

```bash
cd backend
DATABASE_URL=postgresql://... python -m app.rag.ingest   # or REDIS_URL=...
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
database; without it, the index falls back to Redis and then to memory (neither tracks
fingerprints, so for those a sync is a full rebuild). If you deploy before ingesting, the
server logs an error and retrieval returns nothing — `/health` reports `rag_chunks: 0`.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev                 # http://localhost:3000
```

Then open http://localhost:3000 → **Start intake** → eligibility results → dashboard.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | status + whether Postgres/Redis/LLM are configured + RAG chunk count |
| POST | `/api/intake` | create/update a CaseProfile |
| GET | `/api/case/{id}` | fetch a CaseProfile |
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

- **Postgres:** set `DATABASE_URL`; accounts, CaseProfiles, and the Band room map move out of
  memory into the `users`, `cases`, and `band_rooms` tables (created on first use), and the
  same database serves the pgvector RAG index.
- **Redis:** set `REDIS_URL` to persist reminders, care records, and application state; it is
  also the RAG index fallback when `DATABASE_URL` is unset.
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
- Run `npx skills add redis/agent-skills` so AI writes Redis code the Redis-expert way.
```
