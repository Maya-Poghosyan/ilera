import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agents.routing import run_routing
from .config import get_settings
from .forms.filler import resolve_fields
from .integrations import poke
from .intake import INTAKE_SCHEMA, map_answers_to_profile
from .models import CaseProfile, EligibilityResult, FollowupQuestion
from .rag.embeddings import provider as embedding_provider
from .rag.index import get_index
from .store import get_profile, save_profile

settings = get_settings()
app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    index = get_index()
    return {
        "status": "ok",
        "redis": settings.has_redis,
        "llm": settings.has_llm,
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
    )


class RagQuery(BaseModel):
    query: str
    k: int = 4


@app.post("/api/rag/search")
def rag_search(q: RagQuery) -> dict:
    hits = get_index().search(q.query, k=q.k)
    return {
        "results": [
            {"text": h.text, "program": h.program, "source": h.source, "score": round(h.score, 4)}
            for h in hits
        ]
    }


@app.get("/api/forms/{program}/{case_id}")
def form_fields(program: str, case_id: str) -> dict:
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return resolve_fields(program, profile)


class ReminderRequest(BaseModel):
    message: str


@app.post("/api/reminders/send")
def send_reminder(req: ReminderRequest) -> dict:
    if not poke.available():
        raise HTTPException(status_code=400, detail="POKE_API_KEY not configured")
    try:
        result = poke.send_message(req.message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Poke send failed: {exc}") from exc
    return {"sent": True, "poke": result}
