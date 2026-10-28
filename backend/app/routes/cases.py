"""Intake, the case it creates, and the Durable eligibility run over that case."""

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..access import require_case_access
from ..geo import normalize_county, zip_to_county
from ..intake import INTAKE_SCHEMA, map_answers_to_profile
from ..models import CaseProfile, EligibilityResult, EligibilityStatus
from ..store import get_profile, save_profile

logger = logging.getLogger("ilera.scheduler")

router = APIRouter()


@router.get("/api/intake/schema")
def intake_schema() -> dict:
    """Topic-based intake with per-question follow-ups and stable answer IDs."""
    return INTAKE_SCHEMA


@router.get("/api/geo/county")
def lookup_county(zip: str, state: str = "") -> dict:
    """Best-guess county for a ZIP, so the intake can prefill it for confirmation."""
    return {"county": normalize_county(zip_to_county(zip, state))}


class IntakeRequest(BaseModel):
    model_config = {"extra": "forbid"}
    answers: dict[str, Any]


@router.post("/api/intake", response_model=CaseProfile)
async def submit_intake(req: IntakeRequest) -> CaseProfile:
    from ..intake.logic import validate_answers
    try:
        answers = validate_answers(req.answers, complete=True)
    except ValueError:
        raise HTTPException(422, "Invalid or incomplete intake answers") from None
    profile = CaseProfile(id=str(uuid.uuid4()))
    map_answers_to_profile(answers, profile)
    save_profile(profile)
    await _ensure_eligibility_started(profile.id)
    return get_profile(profile.id) or profile


@router.get("/api/case/{case_id}", response_model=CaseProfile)
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


@router.post("/api/eligibility/{case_id}", response_model=EligibilityResponse)
async def determine_eligibility(
    case_id: str, _: str = Depends(require_case_access)
) -> EligibilityResponse:
    """Start (idempotently) the Durable eligibility orchestration and return current status.
    Poll GET /api/eligibility/{case_id} until status is complete."""
    profile = await _ensure_eligibility_started(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return _eligibility_response(profile)


@router.get("/api/eligibility/{case_id}", response_model=EligibilityResponse)
def get_eligibility(
    case_id: str, _: str = Depends(require_case_access)
) -> EligibilityResponse:
    """Read the current eligibility status/results/strategy for a case (safe to poll)."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return _eligibility_response(profile)
