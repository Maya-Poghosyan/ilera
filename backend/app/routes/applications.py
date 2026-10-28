from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..access import require_case_access
from ..applications import (
    AppStatus,
    ApplicationState,
    complete_application,
    get_app_state,
    get_program_forms,
    list_app_states,
    list_programs,
    save_app_state,
    start_application,
    submit_answers,
)
from ..store import get_profile

router = APIRouter()


@router.get("/api/applications/programs")
def api_list_programs() -> dict:
    """List all programs with their form sets."""
    return {"programs": list_programs()}


@router.get("/api/applications/{case_id}")
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


@router.patch("/api/applications/{case_id}/{program}")
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


@router.post("/api/applications/{case_id}/{program}/start")
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


@router.post("/api/applications/{case_id}/{program}/submit")
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


@router.post("/api/applications/{case_id}/{program}/complete")
def api_complete_application(
    case_id: str, program: str, _: str = Depends(require_case_access)
) -> dict:
    """Mark application as completed."""
    complete_application(case_id, program)
    return {"program": program, "status": "completed"}


@router.post("/api/applications/{case_id}/{program}/preview")
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
