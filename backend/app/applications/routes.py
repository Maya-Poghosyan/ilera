from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from app.accounts.access import require_case_access
from app.applications.service import (canonical_program, complete_application, get_program_forms, list_programs, program_is_active, start_application,
                                      submit_answers)
from app.applications.documents import DocumentAnswers, read_application_document
from app.applications.profile_facts import apply_facts, is_fact
from app.applications.state import AppStatus, ApplicationStage, ApplicationState, get_app_state, list_app_states, save_app_state
from app.cases.models import EligibilityResult
from app.cases.store import get_profile, mutate_profile
from app.core import db
from app.intake.documents.models import HTTP_STATUS, DocumentError, ErrorCode
from app.intake.documents.routes import _read_body, spend_limit
from app.intake.documents.upload import Upload
from app.records.service import RenewalItem, list_renewal_items, save_renewal_item

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
    seen: set[str] = set()
    candidates: list[tuple[str, EligibilityResult | None]] = sorted(
        profile.eligibility.items(), key=lambda pair: pair[1].confidence, reverse=True
    )
    candidates += [
        (name, None) for name, state in existing.items()
        if name not in profile.eligibility
        and state.status in (AppStatus.pending_determination, AppStatus.accepted, AppStatus.denied, AppStatus.archived)
    ]
    for name, eligibility in candidates:
        program_name = canonical_program(name)
        state = existing.get(program_name) or existing.get(name)
        tracking_decision = state and state.status in (
            AppStatus.pending_determination, AppStatus.accepted, AppStatus.denied, AppStatus.archived
        )
        if program_name in seen or (program_is_active(profile, program_name) and not tracking_decision):
            continue
        seen.add(program_name)
        forms = get_program_forms(program_name)
        decision_status = state.pre_archive_status if state and state.status == AppStatus.archived else state.status if state else None
        determination = {AppStatus.accepted: "approved", AppStatus.denied: "denied"}.get(decision_status)
        apps.append({
            "program": program_name,
            "determination": determination,
            "status": state.status if state else "open",
            "form_ids": forms,
            "renewal_record_id": state.renewal_record_id if state else None,
            "stage": state.stage if state else ("update_information" if forms else "follow_up"),
            "ready_documents": state.ready_documents if state else [],
            "completed_follow_ups": state.completed_follow_ups if state else [],

            "eligibility_status": eligibility.status if eligibility else None,
            "confidence": eligibility.confidence if eligibility else 0,
            "rationale": eligibility.rationale if eligibility else "",
            "roadblocks": eligibility.roadblocks if eligibility else [],
            "required_documents": eligibility.required_documents if eligibility else [],
            "next_steps": eligibility.next_steps if eligibility else [],
            "sources": eligibility.sources if eligibility else [],
            "has_forms": len(forms) > 0,
        })
    return {"applications": apps}


class ProgressUpdate(BaseModel):
    stage: ApplicationStage
    answers: dict[str, Any] | None = None
    ready_documents: list[str] | None = Field(default=None, max_length=100)
    completed_follow_ups: list[str] | None = Field(default=None, max_length=100)


@router.put("/api/applications/{case_id}/{program}/progress")
def api_save_progress(
    case_id: str, program: str, body: ProgressUpdate, _: str = Depends(require_case_access)
) -> dict:
    program = canonical_program(program)
    profile = get_profile(case_id)
    result = next((result for name, result in profile.eligibility.items()
                   if canonical_program(name) == program), None) if profile else None
    if result is None:
        raise HTTPException(404, "Program application not found")
    state = get_app_state(case_id, program) or ApplicationState(case_id=case_id, program=program)
    if body.answers is not None:
        allowed = {question.field_id for question in state.questions}
        if body.answers.keys() - allowed:
            raise HTTPException(422, "Unknown application answer")
        facts = {k: v for k, v in body.answers.items() if is_fact(k)}
        answers = {k: v for k, v in body.answers.items() if not is_fact(k)}
        state.answers.update(answers)

        # Personal details go to the profile; form answers are also shared with other applications.
        def share(current):
            apply_facts(current, facts)
            current.application_answers.update(answers)
            return current, None
        try:
            mutate_profile(case_id, share)
        except ValueError:
            raise HTTPException(422, "Invalid personal details") from None
    if body.ready_documents is not None:
        state.ready_documents = [item for item in dict.fromkeys(body.ready_documents) if item in result.required_documents]
    if body.completed_follow_ups is not None:
        state.completed_follow_ups = [item for item in dict.fromkeys(body.completed_follow_ups) if item in result.next_steps]
    state.stage = body.stage
    if state.status in (AppStatus.open, AppStatus.needs_info):
        state.status = AppStatus.in_progress
    save_app_state(state)
    return {"stage": state.stage, "status": state.status}


class ApprovalDetails(BaseModel):
    approval_date: date | None = None
    effective_date: date | None = None
    due_date: date | None = None
    benefit_end_date: date | None = None
    tax_year: int | None = Field(default=None, ge=1900, le=2100)

    @model_validator(mode="after")
    def valid_benefit_period(self):
        if self.effective_date and self.benefit_end_date and self.benefit_end_date < self.effective_date:
            raise ValueError("Benefit end date must be on or after the effective date")
        return self


class StatusUpdate(BaseModel):
    status: AppStatus | Literal["restore"]
    approval: ApprovalDetails | None = None


def record_approval(case_id: str, program: str, details: ApprovalDetails) -> ApplicationState:
    # Serialize approvals for the case and save both records in one transaction.
    with db.connection() as conn:
        if not conn.execute("SELECT id FROM cases WHERE id = %s FOR UPDATE", (case_id,)).fetchone():
            raise HTTPException(404, "Case not found")
        state = get_app_state(case_id, program, transaction=conn)
        if state is None or state.status not in (AppStatus.pending_determination, AppStatus.accepted):
            raise HTTPException(409, "Mark the application pending determination before recording approval")
        records = list_renewal_items(case_id, transaction=conn)
        record = next((item for item in records if item.id == state.renewal_record_id
                       or item.source_application == program), None)
        if record is None:
            candidates = [item for item in records if not item.source_application
                          and canonical_program(item.program) == program]
            record = candidates[0] if len(candidates) == 1 else RenewalItem(case_id=case_id, program=program)
        values = details.model_dump(mode="json", exclude_none=True)
        if program in ("Paid Family Leave", "Caregiver Tax Relief"):
            values.pop("due_date", None)
        record.source_application = program
        for field, value in values.items():
            if getattr(record, field) is None:
                setattr(record, field, value)
        save_renewal_item(record, transaction=conn)
        state.renewal_record_id = record.id
        state.status = AppStatus.accepted
        state.pre_archive_status = None
        save_app_state(state, transaction=conn)
    return state


@router.patch("/api/applications/{case_id}/{program}")
def api_update_app_status(
    case_id: str,
    program: str,
    body: StatusUpdate,
    _: str = Depends(require_case_access),
) -> dict:
    """Update the status of an application."""
    program = canonical_program(program)
    if body.status == AppStatus.accepted:
        state = record_approval(case_id, program, body.approval or ApprovalDetails())
        return {"program": program, "status": state.status, "renewal_record_id": state.renewal_record_id}
    with db.connection() as conn:
        if not conn.execute("SELECT id FROM cases WHERE id = %s FOR UPDATE", (case_id,)).fetchone():
            raise HTTPException(404, "Case not found")
        state = get_app_state(case_id, program, transaction=conn)
        if state is None:
            state = ApplicationState(case_id=case_id, program=program)
        if body.status == AppStatus.denied and state.status not in (AppStatus.pending_determination, AppStatus.denied):
            raise HTTPException(409, "Mark the application pending determination before recording denial")
        if body.status == "restore":
            if state.status == AppStatus.archived:
                state.status = state.pre_archive_status or AppStatus.open
                state.pre_archive_status = None
        elif body.status == AppStatus.archived:
            if state.status != AppStatus.archived:
                state.pre_archive_status = state.status
                state.status = AppStatus.archived
        else:
            state.status = body.status
            state.pre_archive_status = None
        save_app_state(state, transaction=conn)
    return {"program": program, "status": state.status}


@router.post("/api/applications/{case_id}/{program}/start")
def api_start_application(
    case_id: str, program: str, _: str = Depends(require_case_access)
) -> dict:
    """Start an application: autofill forms and return missing questions."""
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="case not found")
    return start_application(case_id, canonical_program(program), profile)


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
    pdf_bytes = submit_answers(case_id, canonical_program(program), body.answers, profile)
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
    status = complete_application(case_id, canonical_program(program))
    return {"program": program, "status": status}


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
    pdf_bytes = submit_answers(case_id, canonical_program(program), body.answers, profile)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
    )


@router.post("/api/applications/{case_id}/{program}/documents", response_model=DocumentAnswers)
async def api_read_application_document(
    case_id: str, program: str, request: Request, _: str = Depends(require_case_access)
) -> DocumentAnswers:
    """Read one document (the raw request body) in memory and propose answers to this application's questions.

    - Nothing is stored or logged; the caregiver reviews and saves answers through `/progress`
    """
    state = get_app_state(case_id, canonical_program(program))
    if state is None or not state.questions:
        raise HTTPException(409, "Open the application before adding documents")
    try:
        upload = Upload.parse(await _read_body(request))
        if not spend_limit.allow():
            raise DocumentError(ErrorCode.RATE_LIMITED)
        return await run_in_threadpool(read_application_document, upload, state.questions)
    except DocumentError as err:
        raise HTTPException(HTTP_STATUS[err.code], err.code.value) from None
