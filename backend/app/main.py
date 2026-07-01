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
from .agents.routing import run_routing
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
from .integrations import poke
from .intake import INTAKE_SCHEMA, map_answers_to_profile
from .mcp_server import mcp as mcp_server
from .models import CaseProfile, EligibilityResult, FollowupQuestion, InteractionNote
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
    if settings.has_band or _band_registry_exists():
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
    """Start Band agents in the background so they appear active on the dashboard."""
    try:
        from .integrations.band import build_agents
    except Exception:
        logger.warning("Band SDK not available — skipping agent startup")
        return
    try:
        agents = build_agents()
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


class IntakeRequest(BaseModel):
    profile: CaseProfile | None = None
    answers: dict[str, Any] | None = None


@app.post("/api/intake", response_model=CaseProfile)
def submit_intake(req: IntakeRequest) -> CaseProfile:
    profile = req.profile or CaseProfile(id=str(uuid.uuid4()))
    if not profile.id:
        profile.id = str(uuid.uuid4())
    if req.answers is not None:
        map_answers_to_profile(req.answers, profile)
    save_profile(profile)
    return profile


@app.get("/api/case/{case_id}", response_model=CaseProfile)
def read_case(case_id: str) -> CaseProfile:
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return profile


class EligibilityResponse(BaseModel):
    results: list[EligibilityResult]
    followups: list[FollowupQuestion]
    strategy_notes: list[str]
    interaction_notes: list[InteractionNote]


# Track agent executions for the Band dashboard
_agent_executions: list[dict] = []


async def _dispatch_to_band(profile: CaseProfile) -> None:
    """Send the eligibility request to Band agents so executions register on the dashboard."""
    try:
        from .integrations.band import _SPECIALIST_NAMES, load_registry

        from band.client.rest import (
            AsyncRestClient,
            ChatMessageRequest,
            ChatMessageRequestMentionsItem,
            ChatRoomRequest,
            DEFAULT_REQUEST_OPTIONS,
            ParticipantRequest,
        )

        registry = load_registry()
        routing_creds = registry.get("routing")
        if not routing_creds:
            return
        client = AsyncRestClient(
            api_key=routing_creds["api_key"],
            base_url=get_settings().band_rest_url.rstrip("/"),
        )

        # Fetch routing agent's identity so we know its handle
        me = await client.agent_api_identity.get_agent_me(
            request_options=DEFAULT_REQUEST_OPTIONS
        )
        owner_handle = getattr(me, "owner_handle", None) or getattr(me, "handle", "")

        # Create a chat room
        chat = await client.agent_api_chats.create_agent_chat(
            chat=ChatRoomRequest(), request_options=DEFAULT_REQUEST_OPTIONS
        )
        chat_id = chat.data.id

        # Add specialist agents as participants and build mention items
        mentions: list[ChatMessageRequestMentionsItem] = []
        handle_tags: list[str] = []
        for key, creds in registry.items():
            if key == "routing":
                continue
            try:
                await client.agent_api_participants.add_agent_chat_participant(
                    chat_id,
                    participant=ParticipantRequest(
                        participant_id=creds["agent_id"], role="member"
                    ),
                    request_options=DEFAULT_REQUEST_OPTIONS,
                )
                agent_name = _SPECIALIST_NAMES.get(key, key)
                handle = f"{owner_handle}/{agent_name}" if owner_handle else agent_name
                mentions.append(
                    ChatMessageRequestMentionsItem(
                        id=creds["agent_id"], handle=handle
                    )
                )
                handle_tags.append(f"@{handle}")
            except Exception:
                logger.debug("Could not add specialist %s to room", key, exc_info=True)

        if not mentions:
            logger.warning("Band dispatch: no specialist agents could be added")
            return

        # Compose message with @mentions so agents are properly activated
        cr = profile.care_recipient
        cg = profile.caregiver
        mention_prefix = " ".join(handle_tags)
        msg = (
            f"{mention_prefix} "
            f"Assess eligibility for {cr.name or 'care recipient'}, "
            f"age {cr.age or 'unknown'}, {cr.state}. "
            f"Insurance: {cr.insurance}. "
            f"Care needs: {', '.join(cr.care_needs) or 'unspecified'}. "
            f"Veteran: {cr.veteran}. "
            f"Caregiver: {cg.name or 'family member'} ({cg.relationship}). "
            f"Household income: ${profile.household.income_monthly or 0}/mo."
        )
        await client.agent_api_messages.create_agent_chat_message(
            chat_id,
            message=ChatMessageRequest(content=msg, mentions=mentions),
            request_options=DEFAULT_REQUEST_OPTIONS,
        )
        logger.info("Band dispatch: sent to %d specialists in room %s", len(mentions), chat_id)
    except Exception:
        logger.warning("Band dispatch failed", exc_info=True)


@app.post("/api/eligibility/{case_id}", response_model=EligibilityResponse)
def determine_eligibility(case_id: str) -> EligibilityResponse:
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    routing = run_routing(profile)
    profile.eligibility = {r.program: r for r in routing.results}
    save_profile(profile)
    # Log agent executions
    now = datetime.now(timezone.utc).isoformat()
    for r in routing.results:
        _agent_executions.append({
            "agent": r.program,
            "case_id": case_id,
            "status": r.status,
            "confidence": r.confidence,
            "timestamp": now,
        })
    # Dispatch to Band in background (registers executions on the dashboard)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_dispatch_to_band(profile))
    except RuntimeError:
        pass
    return EligibilityResponse(
        results=routing.results,
        followups=routing.followups,
        strategy_notes=routing.strategy_notes,
        interaction_notes=routing.interaction_notes,
    )


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
    answers: dict[str, str]


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
    """Ask Poke to scan the user's messages/emails for medical events."""
    if not poke.available():
        raise HTTPException(status_code=400, detail="POKE_API_KEY not configured")
    try:
        result = poke.scan_for_events()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Poke scan failed: {exc}") from exc
    return {"scanned": True, "poke": result}



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
