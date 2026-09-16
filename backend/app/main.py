import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import date as Date
from typing import Literal

from .access import authorize_case, require_case_access
from .auth import User, get_current_user, get_optional_user
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
from . import db
from .config import get_settings
from .email_ingestion.routes import router as email_router
from .email_ingestion.notifications import router as email_notifications_router
from .email_ingestion.privacy import configure_email_access_logging
from .forms.filler import fill_pdf, list_schemas, resolve_fields
from .geo import normalize_county, zip_to_county
from .intake import INTAKE_SCHEMA, map_answers_to_profile
from .models import CaseProfile, EligibilityResult, EligibilityStatus
from .rag.embeddings import provider as embedding_provider
from .rag.index import get_index
from .reminders import (
    TEMPLATES,
    Reminder,
    ReminderKind,
    ReminderSchedule,
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
    get_timekeeping,
    get_journal,
    list_journal,
    list_timekeeping,
    save_journal,
    save_renewal,
    save_timekeeping,
)
from .preferences import Preferences, get_preferences, save_preferences
from .store import get_case_id_for_user, get_profile, purge_unclaimed_cases, save_profile
from .suggested_events import (
    SuggestedEvent,
    delete_suggested_event,
    get_suggested_event,
    list_suggested_events,
)

logger = logging.getLogger("ilera.scheduler")

settings = get_settings()

_PURGE_INTERVAL = 24 * 60 * 60  # seconds between unclaimed-case sweeps


async def _purge_loop() -> None:
    """Drop cases whose intake was abandoned before anyone signed up."""
    while True:
        try:
            await asyncio.sleep(_PURGE_INTERVAL)
            deleted = await asyncio.to_thread(
                purge_unclaimed_cases, settings.unclaimed_case_ttl_days
            )
            if deleted:
                logger.info("Purged %d unclaimed case(s)", deleted)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Unclaimed-case purge failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    purge_task = asyncio.create_task(_purge_loop())
    yield
    purge_task.cancel()
    for background in (purge_task,):
        try:
            await background
        except asyncio.CancelledError:
            pass


app = FastAPI(title=settings.app_name, lifespan=lifespan)
configure_email_access_logging()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth routes
app.include_router(auth_router)
app.include_router(email_router)
app.include_router(email_notifications_router)


@app.get("/healthz")
def healthz() -> dict:
    """Liveness only — cheap enough for a platform health check."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz(response: Response) -> dict:
    """Readiness: can this replica actually serve requests?

    Separate from /healthz because the answers differ. A replica whose DATABASE_URL is wrong
    accepts connections and passes liveness, but every case it is handed is lost, so it must
    not receive traffic — answering 503 here keeps the previous good revision serving instead.
    Costs one SELECT 1, so it is cheap enough to poll every few seconds.
    """
    postgres = db.ready()
    if postgres is False:
        response.status_code = 503
    return {"status": "ok" if postgres is not False else "unavailable", "postgres": postgres}


@app.get("/health")
def health() -> dict:
    """Configuration report, including whether RAG can actually serve.

    Attaches to the index rather than waiting for the first query to do it, so a store that is
    unreachable or was never ingested shows up here instead of as silently empty retrieval.
    Attaching costs a count query; nothing here can build an index.
    """
    index = get_index()
    return {
        "status": "ok",
        "postgres": db.ready(),
        "llm": settings.has_llm,

        "embeddings": embedding_provider(),
        "rag_ready": index.size > 0,
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
    await _ensure_eligibility_started(profile.id)
    return get_profile(profile.id) or profile


@app.get("/api/case/{case_id}", response_model=CaseProfile)
def read_case(case_id: str, _: str = Depends(require_case_access)) -> CaseProfile:
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return profile


class EligibilityResponse(BaseModel):
    status: EligibilityStatus
    results: list[EligibilityResult]
    strategy: str = ""
    strategy_complete: bool = False
    expected: list[str] = []
    completed: list[str] = []
    error: str = ""


async def _ensure_eligibility_started(case_id: str) -> Optional[CaseProfile]:
    """Start the Durable eligibility orchestration for a case if it hasn't been started yet.
    Idempotent — Durable uses a deterministic instance ID so a duplicate call is a no-op."""
    from durable.client import start_eligibility_orchestration

    profile = get_profile(case_id)
    if profile is None:
        return None
    if profile.eligibility_status in ("idle", "error"):
        profile.eligibility_status = "processing"
        profile.eligibility_error = ""
        save_profile(profile)
        try:
            await start_eligibility_orchestration(profile)
        except Exception as exc:
            logger.exception("Failed to start Durable orchestration for case %s", case_id)
            p = get_profile(case_id)
            if p is not None:
                p.eligibility_status = "error"
                p.eligibility_error = f"Could not start eligibility processing: {exc}"
                save_profile(p)
    return get_profile(case_id)


def _eligibility_response(profile: CaseProfile) -> EligibilityResponse:
    expected = list(profile.findings.keys())
    completed = [k for k, f in profile.findings.items() if f.complete]
    # Order results strongest-match first for display.
    order = {"very_likely": 0, "likely": 1, "medium": 2, "low": 3, "none": 4}
    results = sorted(
        profile.eligibility.values(),
        key=lambda r: order.get(r.match_level, 5),
    )
    return EligibilityResponse(
        status=profile.eligibility_status,
        results=results,
        strategy=profile.strategy,
        strategy_complete=profile.strategy_complete,
        expected=expected,
        completed=completed,
        error=profile.eligibility_error,
    )


@app.post("/api/eligibility/{case_id}", response_model=EligibilityResponse)
async def determine_eligibility(
    case_id: str, _: str = Depends(require_case_access)
) -> EligibilityResponse:
    """Start (idempotently) the Durable eligibility orchestration and return current status.
    Poll GET /api/eligibility/{case_id} until status is complete."""
    profile = await _ensure_eligibility_started(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return _eligibility_response(profile)


@app.get("/api/eligibility/{case_id}", response_model=EligibilityResponse)
def get_eligibility(
    case_id: str, _: str = Depends(require_case_access)
) -> EligibilityResponse:
    """Read the current eligibility status/results/strategy for a case (safe to poll)."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return _eligibility_response(profile)



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


@app.get("/api/forms")
def list_forms() -> dict:
    """List all available forms with metadata."""
    return {"forms": list_schemas()}


@app.get("/api/forms/{form_id}/{case_id}")
def form_fields(form_id: str, case_id: str, _: str = Depends(require_case_access)) -> dict:
    """Resolve field values for a form against a CaseProfile."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return resolve_fields(form_id, profile)


@app.get("/api/forms/{form_id}/{case_id}/download")
def download_filled_form(
    form_id: str, case_id: str, _: str = Depends(require_case_access)
) -> Response:
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
# Reminder CRUD (delivery is not configured)
# ---------------------------------------------------------------------------


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
def api_list_reminders(case_id: Optional[str] = None, user: Optional[User] = Depends(get_optional_user)) -> list[Reminder]:
    scope = case_id or (get_case_id_for_user(user.id) if user else None)
    if not scope:
        return []
    authorize_case(scope, user)
    return [r for r in list_reminders() if r.case_id == scope]


@app.post("/api/reminders", status_code=201)
def api_create_reminder(
    body: ReminderCreate, user: Optional[User] = Depends(get_optional_user)
) -> Reminder:
    scope = body.case_id or (get_case_id_for_user(user.id) if user else None)
    if not scope:
        raise HTTPException(status_code=422, detail="A case is required")
    authorize_case(scope, user)
    reminder = Reminder(
        case_id=scope,
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
def api_get_reminder(reminder_id: str, user: Optional[User] = Depends(get_optional_user)) -> Reminder:
    r = get_reminder(reminder_id)
    if r is None or not r.case_id:
        raise HTTPException(status_code=404, detail="reminder not found")
    authorize_case(r.case_id, user)
    return r


@app.patch("/api/reminders/{reminder_id}")
def api_patch_reminder(reminder_id: str, body: ReminderUpdate, user: Optional[User] = Depends(get_optional_user)) -> Reminder:
    r = get_reminder(reminder_id)
    if r is None or not r.case_id:
        raise HTTPException(status_code=404, detail="reminder not found")
    authorize_case(r.case_id, user)
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
def api_delete_reminder(reminder_id: str, user: Optional[User] = Depends(get_optional_user)) -> dict:
    api_get_reminder(reminder_id, user)
    if not delete_reminder(reminder_id):
        raise HTTPException(status_code=404, detail="reminder not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


@app.get("/api/applications/programs")
def api_list_programs() -> dict:
    """List all programs with their form sets."""
    return {"programs": list_programs()}


@app.get("/api/applications/{case_id}")
def api_list_applications(case_id: str, _: str = Depends(require_case_access)) -> dict:
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
def api_update_app_status(
    case_id: str,
    program: str,
    body: StatusUpdate,
    _: str = Depends(require_case_access),
) -> dict:
    """Update the status of an application."""
    state = get_app_state(case_id, program)
    if state is None:
        state = ApplicationState(case_id=case_id, program=program)
    state.status = body.status
    save_app_state(state)
    return {"program": program, "status": state.status}


@app.post("/api/applications/{case_id}/{program}/start")
def api_start_application(
    case_id: str, program: str, _: str = Depends(require_case_access)
) -> dict:
    """Start an application: autofill forms and return missing questions."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return start_application(case_id, program, profile)


class AnswersSubmit(BaseModel):
    answers: dict[str, Any]


@app.post("/api/applications/{case_id}/{program}/submit")
def api_submit_answers(
    case_id: str,
    program: str,
    body: AnswersSubmit,
    _: str = Depends(require_case_access),
) -> Response:
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
def api_complete_application(
    case_id: str, program: str, _: str = Depends(require_case_access)
) -> dict:
    """Mark application as completed."""
    complete_application(case_id, program)
    return {"program": program, "status": "completed"}


@app.post("/api/applications/{case_id}/{program}/preview")
def api_preview_stitched(
    case_id: str,
    program: str,
    body: AnswersSubmit,
    _: str = Depends(require_case_access),
) -> Response:
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
# Caregiver preferences
# ---------------------------------------------------------------------------


@app.get("/api/preferences/{case_id}")
def api_get_preferences(case_id: str, _: str = Depends(require_case_access)) -> Preferences:
    return get_preferences(case_id)


class PreferencesUpdate(BaseModel):
    monitor_inboxes: bool


@app.put("/api/preferences/{case_id}")
def api_set_preferences(
    case_id: str, body: PreferencesUpdate, _: str = Depends(require_case_access)
) -> Preferences:
    prefs = get_preferences(case_id)
    prefs.monitor_inboxes = body.monitor_inboxes
    prefs.monitor_inboxes_updated_at = datetime.now(timezone.utc).isoformat()
    return save_preferences(prefs)


# ---------------------------------------------------------------------------
# Suggested events (provider-independent storage)
# ---------------------------------------------------------------------------


@app.get("/api/suggested-events")
def api_list_suggested_events(
    user: User = Depends(get_current_user),
) -> list[SuggestedEvent]:
    # Unowned legacy suggestions remain stored, but cannot safely be assigned to a user.
    return list_suggested_events(user_id=user.id)


@app.delete("/api/suggested-events/{event_id}")
def api_delete_suggested_event(
    event_id: str, user: User = Depends(get_current_user)
) -> dict:
    event = get_suggested_event(event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status_code=404, detail="suggested event not found")
    if not delete_suggested_event(event_id):
        raise HTTPException(status_code=404, detail="suggested event not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Records & Renewal
# ---------------------------------------------------------------------------


class TimekeepingCreate(BaseModel):
    case_id: str
    date: str
    hours: float = Field(gt=0, le=24, allow_inf_nan=False)
    start_time: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    service_type: Literal["personal_care", "domestic", "paramedical", "accompaniment"] = "personal_care"
    tasks: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        if Date.fromisoformat(value).isoformat() != value:
            raise ValueError("Use YYYY-MM-DD")
        return value

    @model_validator(mode="after")
    def valid_duration(self):
        if bool(self.start_time) != bool(self.end_time):
            raise ValueError("Provide both start and end times")
        if self.start_time and self.end_time:
            start = sum(int(v) * m for v, m in zip(self.start_time.split(":"), (60, 1)))
            end = sum(int(v) * m for v, m in zip(self.end_time.split(":"), (60, 1)))
            if end <= start or abs(self.hours * 60 - (end - start)) > 0.01:
                raise ValueError("Hours must match the same-day time range; split overnight care into separate dates")
        return self


class JournalCreate(BaseModel):
    case_id: str
    date: str
    text: str = Field(min_length=1, max_length=20000)

    _valid_date = field_validator("date")(TimekeepingCreate.valid_date.__func__)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a journal note")
        return value.strip()


class IncidentReview(BaseModel):
    status: Literal["confirmed", "dismissed", "unreviewed"]


class RenewalUpdate(BaseModel):
    program: Optional[str] = Field(default=None, min_length=1)
    due_date: Optional[str] = None
    status: Optional[Literal["active", "pending", "overdue"]] = None

    @field_validator("due_date")
    @classmethod
    def valid_due_date(cls, value):
        return TimekeepingCreate.valid_date(value) if value is not None else None


@app.get("/api/records/timekeeping/{case_id}")
def api_list_timekeeping(
    case_id: str, _: str = Depends(require_case_access)
) -> list[TimekeepingEntry]:
    return list_timekeeping(case_id)


@app.post("/api/records/timekeeping", status_code=201)
def api_create_timekeeping(
    body: TimekeepingCreate, user: Optional[User] = Depends(get_optional_user)
) -> TimekeepingEntry:
    authorize_case(body.case_id, user)
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
def api_delete_timekeeping(
    entry_id: str, case_id: str, _: str = Depends(require_case_access)
) -> dict:
    if not delete_timekeeping(entry_id, case_id):
        raise HTTPException(status_code=404, detail="timekeeping entry not found")
    return {"deleted": True}


@app.get("/api/records/journal/{case_id}")
def api_list_journal(
    case_id: str, _: str = Depends(require_case_access)
) -> list[JournalEntry]:
    return list_journal(case_id)


@app.post("/api/records/journal", status_code=201)
def api_create_journal(
    body: JournalCreate, user: Optional[User] = Depends(get_optional_user)
) -> JournalEntry:
    authorize_case(body.case_id, user)
    entry = JournalEntry(
        case_id=body.case_id,
        date=body.date,
        text=body.text,
        fall_flagged=_detect_fall(body.text),
    )
    save_journal(entry)
    return entry


@app.delete("/api/records/journal/{entry_id}")
def api_delete_journal(
    entry_id: str, case_id: str, _: str = Depends(require_case_access)
) -> dict:
    if not delete_journal(entry_id, case_id):
        raise HTTPException(status_code=404, detail="journal entry not found")
    return {"deleted": True}


@app.get("/api/records/renewal/{case_id}")
def api_get_renewal(case_id: str, _: str = Depends(require_case_access)) -> RenewalInfo:
    info = get_renewal(case_id)
    if info is None:
        return RenewalInfo(case_id=case_id)
    return info


@app.put("/api/records/renewal/{case_id}")
def api_put_renewal(
    case_id: str, body: RenewalUpdate, _: str = Depends(require_case_access)
) -> RenewalInfo:
    existing = get_renewal(case_id)
    if existing is None:
        existing = RenewalInfo(case_id=case_id)
    if body.program is not None:
        existing.program = body.program
    if "due_date" in body.model_fields_set:
        existing.due_date = body.due_date
    if body.status is not None:
        existing.status = body.status
    save_renewal(existing)
    return existing


@app.get("/api/records/{case_id}")
def api_records_summary(case_id: str, _: str = Depends(require_case_access)) -> dict:
    """Combined summary: timekeeping + journal + renewal + fall_flag."""
    timekeeping = list_timekeeping(case_id)
    journal = list_journal(case_id)
    renewal = get_renewal(case_id) or RenewalInfo(case_id=case_id)
    fall_flag = any(j.fall_flagged and j.incident_status != "dismissed" for j in journal)
    return {
        "timekeeping": timekeeping,
        "journal": journal,
        "renewal": renewal,
        "fall_flag": fall_flag,
    }


@app.put("/api/records/timekeeping/{entry_id}")
def api_update_timekeeping(entry_id: str, body: TimekeepingCreate, user: Optional[User] = Depends(get_optional_user)) -> TimekeepingEntry:
    authorize_case(body.case_id, user)
    existing = get_timekeeping(entry_id, body.case_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="timekeeping entry not found")
    entry = TimekeepingEntry(**body.model_dump(), id=existing.id, created_at=existing.created_at)
    save_timekeeping(entry)
    return entry


@app.put("/api/records/journal/{entry_id}")
def api_update_journal(entry_id: str, body: JournalCreate, user: Optional[User] = Depends(get_optional_user)) -> JournalEntry:
    authorize_case(body.case_id, user)
    existing = get_journal(entry_id, body.case_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="journal entry not found")
    entry = JournalEntry(**body.model_dump(), id=existing.id, created_at=existing.created_at,
                         fall_flagged=_detect_fall(body.text),
                         incident_status=existing.incident_status if body.text == existing.text else "unreviewed")
    save_journal(entry)
    return entry


@app.patch("/api/records/journal/{entry_id}/incident")
def api_review_incident(entry_id: str, body: IncidentReview, case_id: str, _: str = Depends(require_case_access)) -> JournalEntry:
    entry = get_journal(entry_id, case_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="journal entry not found")
    entry.incident_status = body.status
    save_journal(entry)
    return entry
