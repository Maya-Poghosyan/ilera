import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from .agents.routing import run_routing
from .config import get_settings
from .forms.filler import fill_pdf, list_schemas, resolve_fields
from .integrations import poke
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
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


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


class IntakeRequest(BaseModel):
    profile: CaseProfile | None = None


@app.post("/api/intake", response_model=CaseProfile)
def submit_intake(req: IntakeRequest) -> CaseProfile:
    profile = req.profile or CaseProfile(id=str(uuid.uuid4()))
    if not profile.id:
        profile.id = str(uuid.uuid4())
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


@app.post("/api/eligibility/{case_id}", response_model=EligibilityResponse)
def determine_eligibility(case_id: str) -> EligibilityResponse:
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    routing = run_routing(profile)
    profile.eligibility = {r.program: r for r in routing.results}
    save_profile(profile)
    return EligibilityResponse(
        results=routing.results,
        followups=routing.followups,
        strategy_notes=routing.strategy_notes,
        interaction_notes=routing.interaction_notes,
    )


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
