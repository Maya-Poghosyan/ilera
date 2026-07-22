# Ilera — Agentic assistance for caregivers

Ilera helps unpaid caregivers discover, optimize, and apply for state/federal benefits
(IHSS, Medi-Cal, Paid Family Leave, VA, …) using a multi-agent system grounded in
official program documentation, then supports them with a care calendar, timekeeping,
and a document store.

Built for the UC Berkeley AI Hackathon. Tracks: **Band** (multi-agent), **Redis**
(RAG + agent memory + document store), **Poke / Browserbase** (agentic reminders +
browser automation), **Devin** (built with Devin).

## Architecture

```
Next.js frontend  ──REST──▶  FastAPI backend
  intake wizard                 CaseProfile (Redis / in-memory)
  eligibility cards               │
  dashboard                       ├─ Routing Agent ──▶ specialist agents (IHSS, Medi-Cal, PFL, VA)
                                  │       coordinate in a shared agent space (Band)
                                  ├─ RAG over program docs (RedisVL)
                                  └─ form fill + stitch (pypdf / fillpdf)
                          integrations: Poke (SMS/email), Browserbase (portal automation)
```

The **`CaseProfile`** is the shared spine: every agent reads and writes it.

## Repo layout

```
frontend/   Next.js 14 + TS + Tailwind + shadcn/ui
backend/    FastAPI app
  app/
    agents/     routing + specialists + Band shared space
    rag/        embeddings + vector index (RedisVL-ready, in-memory fallback)
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
cp .env.example .env        # optional: add Redis / LLM / Band / Poke / Browserbase keys
uvicorn app.main:app --reload --port 8000
```

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
| GET | `/health` | status + whether Redis/LLM are configured + RAG chunk count |
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

- **Redis:** set `REDIS_URL`; replace the in-memory index in `app/rag/index.py` with a
  RedisVL `SearchIndex`, and back the CaseProfile with the Redis Agent Memory Server.
- **LLM:** set `OPENAI_API_KEY` (real embeddings) and/or `ANTHROPIC_API_KEY`; replace
  heuristic `assess()` bodies in `app/agents/specialists.py` with grounded LLM calls.
- **Band:** wired as a true multi-agent system — **each program group is its own Band agent**
  (IHSS, Medi-Cal, Medicare, PFL, VA, Tax), grounded only in its program's docs, plus a
  routing coordinator. Create a Remote Agent on app.band.ai per group, copy
  `backend/band_agents.example.json` → `backend/band_agents.json`, and fill in each agent's
  UUID + API key. Then `pip install -r requirements-band.txt` and run the worker:
  `python -m app.integrations.band` (it launches every configured agent). Specialists expose
  program-scoped `assesseligibility` + `lookupprogramdocs` tools; the router exposes the
  cross-program `assesseligibility` + `searchprogramdocs`. With no registry file it falls back
  to a single coordinator from `BAND_API_KEY` + `BAND_AGENT_ID`. `app/agents/band_space.py`
  still handles in-process coordination for the synchronous HTTP flow.
- **Poke:** `POKE_API_KEY` is now wired — reminders are delivered. See the Poke section above.
- **Browserbase:** wire IHSS portal automation.
- **Forms:** drop fillable government PDFs into `backend/data/` and fill out the field-map JSONs.
- Run `npx skills add redis/agent-skills` so AI writes Redis code the Redis-expert way.
```
