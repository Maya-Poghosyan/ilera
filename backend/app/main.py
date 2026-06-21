import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agents.routing import run_routing
from .config import get_settings
from .forms.filler import resolve_fields
from .models import CaseProfile, EligibilityResult, FollowupQuestion
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
    return {
        "status": "ok",
        "redis": settings.has_redis,
        "llm": settings.has_llm,
        "rag_chunks": get_index().size,
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
