from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..access import require_case_access
from ..forms.filler import fill_pdf, list_schemas, resolve_fields
from ..forms.readiness import program_readiness
from ..models import EligibilityStatus, FormReadiness
from ..store import get_profile

router = APIRouter()


@router.get("/api/forms")
def list_forms() -> dict:
    """List all available forms with metadata."""
    return {"forms": list_schemas()}


@router.get("/api/forms/{form_id}/{case_id}")
def form_fields(form_id: str, case_id: str, _: str = Depends(require_case_access)) -> dict:
    """Resolve field values for a form against a CaseProfile."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return resolve_fields(form_id, profile)


class FormReadinessResponse(BaseModel):
    status: EligibilityStatus
    programs: list[FormReadiness] = []


@router.get("/api/applications/{case_id}/readiness", response_model=FormReadinessResponse)
def application_readiness(
    case_id: str, _: str = Depends(require_case_access)
) -> FormReadinessResponse:
    """Per-program checklist of documents to gather and info forms will still need.

    A pure projection of the completed eligibility findings — no LLM, no re-run. Lets
    the caregiver start assembling paperwork from the pre-signup summary, and lets the
    forms flow begin from a known checklist. Returns an empty list until eligibility
    completes (status reflects where the run is)."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return FormReadinessResponse(
        status=profile.eligibility_status,
        programs=program_readiness(profile),
    )


@router.get("/api/forms/{form_id}/{case_id}/download")
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
