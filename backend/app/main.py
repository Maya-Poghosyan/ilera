import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from .auth import router as auth_router
from .applications import (
    AppStatus,
    complete_application,
    get_app_state,
    get_program_forms,
    list_app_states,
    list_programs,
    save_app_state,
    start_application,
    submit_answers,
    ApplicationState,
)
from .config import get_settings
from .forms.filler import fill_pdf, list_schemas, resolve_fields
from .geo import normalize_county, zip_to_county
from .integrations import poke
from .intake import INTAKE_SCHEMA, map_answers_to_profile
from .mcp_server import mcp as mcp_server
from .models import BandStatus, CaseProfile, EligibilityResult
from .rag.embeddings import provider as embedding_provider
from .rag.index import get_index, rebuild_index
from .reminders import (
    TEMPLATES,
    Reminder,
    ReminderKind,
    ReminderSchedule,
    advance_next_run,
    compute_next_run,
    delete_reminder,
    get_reminder,
    list_reminders,
    save_reminder,
)
from .records import (
    JournalEntry,
    RenewalInfo,
    TimekeepingEntry,
    _detect_fall,
    delete_journal,
    delete_timekeeping,
    get_renewal,
    list_journal,
    list_timekeeping,
    save_journal,
    save_renewal,
    save_timekeeping,
)
from .store import get_profile, save_profile
from .suggested_events import (
    SuggestedEvent,
    delete_suggested_event,
    list_suggested_events,
)

logger = logging.getLogger("ilera.scheduler")

settings = get_settings()

# ---------------------------------------------------------------------------
# Scheduler — lightweight asyncio background loop
# ---------------------------------------------------------------------------

_SCHEDULER_INTERVAL = 30  # seconds between ticks


async def _scheduler_loop() -> None:
    """Check for due reminders every interval and fire them via Poke."""
    while True:
        try:
            await asyncio.sleep(_SCHEDULER_INTERVAL)
            now = datetime.now(timezone.utc)
            for reminder in list_reminders():
                if not reminder.active or not reminder.next_run:
                    continue
                fire_at = datetime.fromisoformat(reminder.next_run)
                if fire_at > now:
                    continue
                # Determine message
                msg = reminder.message
                if reminder.kind == ReminderKind.daily_care_log and not msg:
                    msg = poke.daily_care_log_prompt()
                if not msg:
                    continue
                # Send via Poke (no-op if key missing)
                if poke.available():
                    try:
                        poke.send_message(msg)
                        logger.info("Sent reminder %s", reminder.id)
                    except Exception:
                        logger.exception("Failed to send reminder %s", reminder.id)
                        continue
                else:
                    logger.debug("Poke not configured — skipping reminder %s", reminder.id)
                # Advance
                reminder.last_sent_at = now.isoformat()
                advance_next_run(reminder)
                save_reminder(reminder)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Scheduler tick error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_scheduler_loop())
    band_task = None
    # Band is the eligibility engine: keep the routing + specialist agents connected for the
    # life of the server so they react to per-case rooms as they are created.
    if settings.has_llm and (settings.has_band or _band_registry_exists()):
        band_task = asyncio.create_task(_band_loop())
    yield
    task.cancel()
    if band_task:
        band_task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    if band_task:
        try:
            await band_task
        except asyncio.CancelledError:
            pass


def _band_registry_exists() -> bool:
    import os
    path = settings.band_agents_file
    if path and not os.path.isabs(path):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path
        )
    return bool(path and os.path.exists(path))


async def _band_loop() -> None:
    """Keep every configured Band agent connected so they react to per-case rooms.

    skip_backlog=True so agents don't reprocess old/orphan rooms on startup; they still
    receive live messages for rooms they're added to after connecting.
    """
    try:
        from .integrations.band import build_agents, leave_all_rooms
    except Exception:
        logger.warning("Band SDK not available — skipping agent startup")
        return
    try:
        agents = build_agents(skip_backlog=True)
        # Leave every existing room before connecting. Old/orphan rooms hold undelivered `pending`
        # backlog that can't be marked processed (see leave_all_rooms); if the agents stay members
        # they re-run a full LLM turn per redelivered message and exhaust the rate limit. Agents
        # are re-added per case (routing in start_case_room, specialists per wave), so they end up
        # resident only in the room they're actively working.
        await leave_all_rooms()
        await asyncio.gather(*(a.start() for _, a in agents))
        names = ", ".join(f"{k}" for k, _ in agents)
        logger.info("Band agents connected: %s", names)
        await asyncio.gather(*(a.run_forever() for _, a in agents))
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Band agents failed")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount MCP server for Poke integration (SSE transport at /mcp)
app.mount("/mcp", mcp_server.sse_app())

# Auth routes
app.include_router(auth_router)


@app.get("/health")
def health() -> dict:
    index = get_index()
    return {
        "status": "ok",
        "redis": settings.has_redis,
        "llm": settings.has_llm,
        "band": settings.has_band,
        "poke": poke.available(),
        "embeddings": embedding_provider(),
        "rag_backend": index.backend,
        "rag_chunks": index.size,
    }


@app.get("/api/intake/schema")
def intake_schema() -> dict:
    """The schema-driven intake: Welcome, Screens 1–9 (Q1–Q42), and Conditional
    Mini-Modules A–F, with field_ids, types, options, and show_when conditions."""
    return INTAKE_SCHEMA


@app.get("/api/geo/county")
def lookup_county(zip: str, state: str = "") -> dict:
    """Best-guess county for a ZIP, so the intake can prefill it for confirmation."""
    return {"county": normalize_county(zip_to_county(zip, state))}


class IntakeRequest(BaseModel):
    profile: CaseProfile | None = None
    answers: dict[str, Any] | None = None


@app.post("/api/intake", response_model=CaseProfile)
async def submit_intake(req: IntakeRequest) -> CaseProfile:
    profile = req.profile or CaseProfile(id=str(uuid.uuid4()))
    if not profile.id:
        profile.id = str(uuid.uuid4())
    if req.answers is not None:
        map_answers_to_profile(req.answers, profile)
    save_profile(profile)
    # Fire up the Band eligibility room for this case as soon as intake is submitted.
    _ensure_eligibility_started(profile.id)
    return get_profile(profile.id) or profile


@app.get("/api/case/{case_id}", response_model=CaseProfile)
def read_case(case_id: str) -> CaseProfile:
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return profile


class EligibilityResponse(BaseModel):
    status: BandStatus
    results: list[EligibilityResult]
    strategy: str = ""
    strategy_complete: bool = False
    expected: list[str] = []
    completed: list[str] = []
    error: str = ""


# Track agent executions for the Band dashboard
_agent_executions: list[dict] = []


# Time budgets for the async Band eligibility run.
_FINDINGS_TIMEOUT = 900  # seconds to wait for ALL specialists to submit complete findings
_STRATEGY_TIMEOUT = 360  # seconds to wait for the routing agent to submit its strategy
_POLL_INTERVAL = 4
_WATCHDOG_INTERVAL = 20   # how often to sweep the room for stuck peer messages
# A specialist-sent peer message older than this that is still un-acked is treated as stale: it
# either finished a bounded cross-eligibility exchange or is a poison message trapping an agent in
# a /next resync loop, so the watchdog force-acks it. Long enough to allow a real one-shot Q&A.
_PEER_MSG_STALE_SECS = 60


def _findings_summary(profile: CaseProfile, specialists: list[str]) -> str:
    parts = []
    for key in specialists:
        f = profile.findings.get(key)
        if f and f.complete:
            notes = " ".join(f.notes)
            parts.append(f"- {f.program}: match={f.match_level}. {notes}")
    return "\n".join(parts)


async def _run_case_eligibility(case_id: str) -> None:
    """Orchestrate one case's Band eligibility run end-to-end:
    create the room + seed, wait for every specialist's complete finding, trigger the routing
    agent to synthesize the strategy, and drive the case's band_status to complete/error.
    Band is the sole engine — there is no in-process fallback."""
    from .integrations.band import (
        drain_routing_queue,
        force_ack_stale_peer_messages,
        seed_specialists,
        settle_room,
        start_case_room,
        trigger_synthesis,
    )

    profile = get_profile(case_id)
    if profile is None:
        return

    profile.band_status = "processing"
    profile.band_started_at = datetime.now(timezone.utc).isoformat()
    profile.band_completed_at = ""
    profile.band_error = ""
    profile.findings = {}
    profile.eligibility = {}
    profile.strategy = ""
    profile.strategy_complete = False
    profile.synthesis_requested = False
    profile.peer_msg_counts = {}
    save_profile(profile)

    try:
        chat_id, specialists = await start_case_room(profile)
    except Exception as exc:  # Band unavailable / misconfigured — surface as error, no fallback
        logger.exception("Band eligibility failed to start for case %s", case_id)
        p = get_profile(case_id)
        if p is not None:
            p.band_status = "error"
            p.band_error = f"Could not start eligibility processing: {exc}"
            save_profile(p)
        return

    p = get_profile(case_id)
    p.band_chat_id = chat_id
    p.expected_specialists = specialists
    save_profile(p)

    # Seed the whole specialist panel with ONE message @mentioning all of them, then wait for
    # every specialist to submit a complete finding. The mention gate means only @mentioned agents
    # run a turn, and specialists may hold a short bounded cross-eligibility conversation before
    # submitting — routing does not re-post per specialist.
    loop = asyncio.get_running_loop()
    all_complete = False
    try:
        await seed_specialists(profile, chat_id, specialists)
    except Exception:
        logger.exception("Band seed failed for case %s", case_id)

    deadline_f = loop.time() + _FINDINGS_TIMEOUT
    next_watchdog = loop.time() + _WATCHDOG_INTERVAL
    while loop.time() < deadline_f:
        await asyncio.sleep(_POLL_INTERVAL)
        p = get_profile(case_id)
        if p is None:
            return
        if all(k in p.findings and p.findings[k].complete for k in specialists):
            all_complete = True
            break
        # Watchdog: clear any stale peer-chatter message that is stuck in a recipient's queue,
        # which would otherwise trap that agent in an infinite /next resync loop and prevent it
        # from ever submitting. Only specialist-sent messages are touched (never the seed).
        if loop.time() >= next_watchdog:
            next_watchdog = loop.time() + _WATCHDOG_INTERVAL
            try:
                await force_ack_stale_peer_messages(chat_id, _PEER_MSG_STALE_SECS)
            except Exception:
                logger.exception("Band peer-message watchdog failed for case %s", case_id)

    p = get_profile(case_id)
    if p is None:
        return

    if not all_complete:
        # Not all specialists finished in time. No fallback / no partial synthesis: surface an
        # error naming who is missing so it can be retried.
        done = [k for k in specialists if k in p.findings and p.findings[k].complete]
        missing = [k for k in specialists if k not in done]
        p.band_status = "error"
        p.band_error = (
            "Specialist evaluation did not complete in time "
            f"(missing: {', '.join(missing) or 'all'})."
        )
        save_profile(p)
        return

    # Clear routing's accumulated backlog (specialist notices it stayed silent on) while it is
    # still gated, THEN open the gate. That way, once synthesis_requested is set, the only
    # unprocessed message routing sees is the synthesis trigger — so it synthesizes exactly once
    # instead of burning a turn per stale @mention.
    try:
        await drain_routing_queue(chat_id)
    except Exception:
        logger.exception("Band drain_routing_queue failed for case %s", case_id)
    p.synthesis_requested = True
    save_profile(p)
    await trigger_synthesis(chat_id, _findings_summary(p, specialists))

    # Wait for the routing agent to submit its strategy (record_strategy sets status=complete).
    deadline = loop.time() + _STRATEGY_TIMEOUT
    while loop.time() < deadline:
        await asyncio.sleep(_POLL_INTERVAL)
        p = get_profile(case_id)
        if p is not None and p.strategy_complete:
            # Phase done: empty this room's queue so a worker restart won't replay its messages
            # and burn quota. The room stays open (reused later for application completion).
            try:
                await settle_room(chat_id)
            except Exception:
                logger.exception("Band settle failed for case %s", case_id)
            return

    # Completion requires a persisted strategy; if routing never delivered one, surface an error.
    p = get_profile(case_id)
    if p is not None and not p.strategy_complete:
        p.band_status = "error"
        p.band_error = "The routing agent did not deliver an application strategy in time."
        save_profile(p)


def _ensure_eligibility_started(case_id: str) -> Optional[CaseProfile]:
    """Start the Band eligibility run for a case if it hasn't been started yet. Idempotent."""
    profile = get_profile(case_id)
    if profile is None:
        return None
    if profile.band_status in ("idle", "error"):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return profile
        # Flip to processing synchronously so a near-simultaneous call doesn't start a 2nd room.
        profile.band_status = "processing"
        profile.band_error = ""
        save_profile(profile)
        loop.create_task(_run_case_eligibility(case_id))
    return profile


def _eligibility_response(profile: CaseProfile) -> EligibilityResponse:
    expected = profile.expected_specialists
    completed = [k for k in expected if k in profile.findings and profile.findings[k].complete]
    # Order results strongest-match first for display.
    order = {"very_likely": 0, "likely": 1, "medium": 2, "low": 3, "none": 4}
    results = sorted(
        profile.eligibility.values(),
        key=lambda r: order.get(r.match_level, 5),
    )
    return EligibilityResponse(
        status=profile.band_status,
        results=results,
        strategy=profile.strategy,
        strategy_complete=profile.strategy_complete,
        expected=expected,
        completed=completed,
        error=profile.band_error,
    )


@app.post("/api/eligibility/{case_id}", response_model=EligibilityResponse)
def determine_eligibility(case_id: str) -> EligibilityResponse:
    """Start (idempotently) the Band eligibility run for a case and return current status.
    Band is the sole engine — poll GET /api/eligibility/{case_id} until status is complete."""
    profile = _ensure_eligibility_started(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return _eligibility_response(profile)


@app.get("/api/eligibility/{case_id}", response_model=EligibilityResponse)
def get_eligibility(case_id: str) -> EligibilityResponse:
    """Read the current eligibility status/results/strategy for a case (safe to poll)."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return _eligibility_response(profile)


@app.get("/api/agents/status")
def agents_status() -> dict:
    """Return which specialist agents have executed and when."""
    from .agents.specialists import ALL_SPECIALISTS
    agents = {}
    for cls in ALL_SPECIALISTS:
        agent = cls()
        runs = [e for e in _agent_executions if e["agent"] == agent.program]
        agents[agent.program] = {
            "doc_key": agent.doc_key,
            "total_runs": len(runs),
            "last_run": runs[-1] if runs else None,
        }
    return {"agents": agents, "band_configured": settings.has_band}


class RagQuery(BaseModel):
    query: str
    k: int = 4


@app.post("/api/rag/search")
def rag_search(q: RagQuery) -> dict:
    hits = get_index().search(q.query, k=q.k)
    return {
        "results": [
            {
                "text": h.text,
                "program": h.program,
                "source": h.source,
                "title": h.title,
                "source_url": h.source_url,
                "document_id": h.document_id,
                "page": h.page,
                "score": round(h.score, 4),
            }
            for h in hits
        ]
    }


@app.post("/api/rag/rebuild")
def rag_rebuild() -> dict:
    index = rebuild_index()
    return {"backend": index.backend, "indexed": index.size}


@app.get("/api/forms")
def list_forms() -> dict:
    """List all available forms with metadata."""
    return {"forms": list_schemas()}


@app.get("/api/forms/{form_id}/{case_id}")
def form_fields(form_id: str, case_id: str) -> dict:
    """Resolve field values for a form against a CaseProfile."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return resolve_fields(form_id, profile)


@app.get("/api/forms/{form_id}/{case_id}/download")
def download_filled_form(form_id: str, case_id: str) -> Response:
    """Stream a filled PDF for the given form and case."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    try:
        pdf_bytes = fill_pdf(form_id, profile)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    filename = f"{form_id}_{case_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Reminder CRUD + send
# ---------------------------------------------------------------------------


class SendMessageRequest(BaseModel):
    message: str


@app.post("/api/reminders/send")
def send_reminder_now(req: SendMessageRequest) -> dict:
    if not poke.available():
        raise HTTPException(status_code=400, detail="POKE_API_KEY not configured")
    try:
        result = poke.send_message(req.message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Poke send failed: {exc}") from exc
    return {"sent": True, "poke": result}


class ReminderCreate(BaseModel):
    case_id: Optional[str] = None
    kind: ReminderKind = ReminderKind.custom
    message: str = ""
    schedule: ReminderSchedule = ReminderSchedule()
    active: bool = True


class ReminderUpdate(BaseModel):
    message: Optional[str] = None
    schedule: Optional[ReminderSchedule] = None
    active: Optional[bool] = None
    kind: Optional[ReminderKind] = None


@app.get("/api/reminders")
def api_list_reminders() -> list[Reminder]:
    return list_reminders()


@app.post("/api/reminders", status_code=201)
def api_create_reminder(body: ReminderCreate) -> Reminder:
    reminder = Reminder(
        case_id=body.case_id,
        kind=body.kind,
        message=body.message,
        schedule=body.schedule,
        active=body.active,
    )
    reminder.next_run = compute_next_run(reminder.schedule)
    save_reminder(reminder)
    return reminder


@app.get("/api/reminders/templates")
def api_templates() -> dict:
    return TEMPLATES


@app.get("/api/reminders/{reminder_id}")
def api_get_reminder(reminder_id: str) -> Reminder:
    r = get_reminder(reminder_id)
    if r is None:
        raise HTTPException(status_code=404, detail="reminder not found")
    return r


@app.patch("/api/reminders/{reminder_id}")
def api_patch_reminder(reminder_id: str, body: ReminderUpdate) -> Reminder:
    r = get_reminder(reminder_id)
    if r is None:
        raise HTTPException(status_code=404, detail="reminder not found")
    if body.message is not None:
        r.message = body.message
    if body.schedule is not None:
        r.schedule = body.schedule
        r.next_run = compute_next_run(r.schedule)
    if body.active is not None:
        r.active = body.active
        if r.active and r.next_run is None:
            r.next_run = compute_next_run(r.schedule)
    if body.kind is not None:
        r.kind = body.kind
    save_reminder(r)
    return r


@app.delete("/api/reminders/{reminder_id}")
def api_delete_reminder(reminder_id: str) -> dict:
    if not delete_reminder(reminder_id):
        raise HTTPException(status_code=404, detail="reminder not found")
    return {"deleted": True}


@app.post("/api/reminders/{reminder_id}/run-now")
def api_run_now(reminder_id: str) -> dict:
    """Immediately fire a reminder via Poke (for demos / testing)."""
    r = get_reminder(reminder_id)
    if r is None:
        raise HTTPException(status_code=404, detail="reminder not found")
    msg = r.message
    if r.kind == ReminderKind.daily_care_log and not msg:
        msg = poke.daily_care_log_prompt()
    if not msg:
        raise HTTPException(status_code=400, detail="reminder has no message")
    if not poke.available():
        raise HTTPException(status_code=400, detail="POKE_API_KEY not configured")
    try:
        result = poke.send_message(msg)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Poke send failed: {exc}") from exc
    r.last_sent_at = datetime.now(timezone.utc).isoformat()
    save_reminder(r)
    return {"sent": True, "poke": result}


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


@app.get("/api/applications/programs")
def api_list_programs() -> dict:
    """List all programs with their form sets."""
    return {"programs": list_programs()}


@app.get("/api/applications/{case_id}")
def api_list_applications(case_id: str) -> dict:
    """List application states for a case, seeded from eligibility results."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    existing = {s.program: s for s in list_app_states(case_id)}
    apps = []
    for program_name in profile.eligibility:
        forms = get_program_forms(program_name)
        state = existing.get(program_name)
        eligibility = profile.eligibility.get(program_name)
        apps.append({
            "program": program_name,
            "status": state.status if state else "open",
            "form_ids": forms,
            "eligibility_status": eligibility.status if eligibility else None,
            "confidence": eligibility.confidence if eligibility else 0,
            "rationale": eligibility.rationale if eligibility else "",
            "roadblocks": eligibility.roadblocks if eligibility else [],
            "required_documents": eligibility.required_documents if eligibility else [],
            "next_steps": eligibility.next_steps if eligibility else [],
            "sources": eligibility.sources if eligibility else [],
            "has_forms": len(forms) > 0,
        })
    apps.sort(key=lambda a: a["confidence"], reverse=True)
    return {"applications": apps}


class StatusUpdate(BaseModel):
    status: AppStatus


@app.patch("/api/applications/{case_id}/{program}")
def api_update_app_status(case_id: str, program: str, body: StatusUpdate) -> dict:
    """Update the status of an application."""
    state = get_app_state(case_id, program)
    if state is None:
        state = ApplicationState(case_id=case_id, program=program)
    state.status = body.status
    save_app_state(state)
    return {"program": program, "status": state.status}


@app.post("/api/applications/{case_id}/{program}/start")
def api_start_application(case_id: str, program: str) -> dict:
    """Start an application: autofill forms and return missing questions."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return start_application(case_id, program, profile)


class AnswersSubmit(BaseModel):
    answers: dict[str, Any]


@app.post("/api/applications/{case_id}/{program}/submit")
def api_submit_answers(case_id: str, program: str, body: AnswersSubmit) -> Response:
    """Submit answers and return the stitched filled PDF."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    pdf_bytes = submit_answers(case_id, program, body.answers, profile)
    filename = f"{program.lower().replace(' ', '_')}_{case_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/applications/{case_id}/{program}/complete")
def api_complete_application(case_id: str, program: str) -> dict:
    """Mark application as completed."""
    complete_application(case_id, program)
    return {"program": program, "status": "completed"}


@app.post("/api/applications/{case_id}/{program}/preview")
def api_preview_stitched(case_id: str, program: str, body: AnswersSubmit) -> Response:
    """Preview the stitched PDF without marking as completed."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    pdf_bytes = submit_answers(case_id, program, body.answers, profile)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
    )


# ---------------------------------------------------------------------------
# Poke message/email scanning → suggested events
# ---------------------------------------------------------------------------


@app.post("/api/poke/scan")
def poke_scan_events() -> dict:
    """Ask Poke to scan the user's messages/emails for medical events.

    Poke works asynchronously and files what it finds by calling the
    ``add_suggested_event`` MCP tool, so this only confirms the request was
    queued — clients should poll ``/api/suggested-events`` for results.
    """
    if not poke.available():
        raise HTTPException(status_code=400, detail="POKE_API_KEY not configured")
    try:
        poke.scan_for_events()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Poke scan failed: {exc}") from exc
    return {"requested": True, "known_event_ids": [e.id for e in list_suggested_events()]}



# ---------------------------------------------------------------------------
# Suggested events (created by Poke via MCP or manually)
# ---------------------------------------------------------------------------


@app.get("/api/suggested-events")
def api_list_suggested_events() -> list[SuggestedEvent]:
    return list_suggested_events()


@app.delete("/api/suggested-events/{event_id}")
def api_delete_suggested_event(event_id: str) -> dict:
    if not delete_suggested_event(event_id):
        raise HTTPException(status_code=404, detail="suggested event not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Records & Renewal
# ---------------------------------------------------------------------------


class TimekeepingCreate(BaseModel):
    case_id: str
    date: str
    hours: float
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    service_type: str = "personal_care"
    tasks: list[str] = []
    notes: str = ""


class JournalCreate(BaseModel):
    case_id: str
    date: str
    text: str


class RenewalUpdate(BaseModel):
    program: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None


@app.get("/api/records/timekeeping/{case_id}")
def api_list_timekeeping(case_id: str) -> list[TimekeepingEntry]:
    return list_timekeeping(case_id)


@app.post("/api/records/timekeeping", status_code=201)
def api_create_timekeeping(body: TimekeepingCreate) -> TimekeepingEntry:
    entry = TimekeepingEntry(
        case_id=body.case_id,
        date=body.date,
        hours=body.hours,
        start_time=body.start_time,
        end_time=body.end_time,
        service_type=body.service_type,
        tasks=body.tasks,
        notes=body.notes,
    )
    save_timekeeping(entry)
    return entry


@app.delete("/api/records/timekeeping/{entry_id}")
def api_delete_timekeeping(entry_id: str, case_id: str) -> dict:
    if not delete_timekeeping(entry_id, case_id):
        raise HTTPException(status_code=404, detail="timekeeping entry not found")
    return {"deleted": True}


@app.get("/api/records/journal/{case_id}")
def api_list_journal(case_id: str) -> list[JournalEntry]:
    return list_journal(case_id)


@app.post("/api/records/journal", status_code=201)
def api_create_journal(body: JournalCreate) -> JournalEntry:
    entry = JournalEntry(
        case_id=body.case_id,
        date=body.date,
        text=body.text,
        fall_flagged=_detect_fall(body.text),
    )
    save_journal(entry)
    return entry


@app.delete("/api/records/journal/{entry_id}")
def api_delete_journal(entry_id: str, case_id: str) -> dict:
    if not delete_journal(entry_id, case_id):
        raise HTTPException(status_code=404, detail="journal entry not found")
    return {"deleted": True}


@app.get("/api/records/renewal/{case_id}")
def api_get_renewal(case_id: str) -> RenewalInfo:
    info = get_renewal(case_id)
    if info is None:
        return RenewalInfo(case_id=case_id)
    return info


@app.put("/api/records/renewal/{case_id}")
def api_put_renewal(case_id: str, body: RenewalUpdate) -> RenewalInfo:
    existing = get_renewal(case_id)
    if existing is None:
        existing = RenewalInfo(case_id=case_id)
    if body.program is not None:
        existing.program = body.program
    if body.due_date is not None:
        existing.due_date = body.due_date
    if body.status is not None:
        existing.status = body.status
    save_renewal(existing)
    return existing


@app.get("/api/records/{case_id}")
def api_records_summary(case_id: str) -> dict:
    """Combined summary: timekeeping + journal + renewal + fall_flag."""
    timekeeping = list_timekeeping(case_id)
    journal = list_journal(case_id)
    renewal = get_renewal(case_id) or RenewalInfo(case_id=case_id)
    fall_flag = any(j.fall_flagged for j in journal)
    return {
        "timekeeping": timekeeping,
        "journal": journal,
        "renewal": renewal,
        "fall_flag": fall_flag,
    }
