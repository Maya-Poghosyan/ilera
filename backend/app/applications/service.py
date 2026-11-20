"""Application completion engine.

Manages the lifecycle of benefit applications: program->form-set mapping,
application status persistence (Postgres), autofill + Q&A resolution,
and stitching multiple filled PDFs into a single combined document.
"""

import io
from typing import Any

from pypdf import PdfWriter

from app.forms.discovery import discover_fields, field_index
from app.forms.filler import load_schema, resolve_fields, write_values
from app.applications.questions import (build_question, group_questions, grouped_values, merge_question, same_fact,
                                         to_pdf_value)
from app.applications.state import AppQuestion, AppStatus, ApplicationState, get_app_state, save_app_state
from app.cases.models import CaseProfile

# ---------------------------------------------------------------------------
# Program -> form-set mapping
# ---------------------------------------------------------------------------

PROGRAM_FORMS: dict[str, list[str]] = {
    "IHSS": ["soc-295", "soc-426a"],
    "VA Caregiver Support": ["va-10-10cg"],
    "Medi-Cal": ["ccfrm604"],
    "CHAMPVA": ["va-10-7959c"],
    "CFRA / FMLA": ["cfra-cert"],
    "IHSS Provider": ["soc-426", "soc-829"],
}


def get_program_forms(program: str) -> list[str]:
    return PROGRAM_FORMS.get(program, [])


def list_programs() -> list[dict[str, Any]]:
    result = []
    for program, form_ids in PROGRAM_FORMS.items():
        result.append({
            "program": program,
            "form_ids": form_ids,
            "form_count": len(form_ids),
        })
    return result


# ---------------------------------------------------------------------------
# Application flow logic
# ---------------------------------------------------------------------------


# Fallback map when a field isn't found in the real PDF (schema spec type -> intake type).


# A record marker names *which* of several like things a question is about: "Person 2",
# "Household Member 1", "Other insurance #2", "Income source 3", "Dependent 2". The
# leading noun and its number together identify the record; two questions about the same
# fact belong to the same person only when both resolve to the same record. "Primary
# contact" is a form's name for the first person, so it is treated as person 1.
# Everything stripped from a label before comparing what it asks: parentheticals, any
# record marker, and bare demonstratives that only make a sentence read naturally.
# Role suffixes on a group id that don't change which record it is about, stripped so a
# section and its opt-in ("..._contact" and "..._contact_opt_in") share one scope.


def start_application(
    case_id: str, program: str, profile: CaseProfile
) -> dict[str, Any]:
    """Start or resume an application: autofill all forms and compose missing questions."""
    form_ids = get_program_forms(program)
    if not form_ids:
        return {
            "program": program,
            "form_ids": [],
            "autofilled": 0,
            "total_fields": 0,
            "questions": [],
            "error": f"No forms mapped for program '{program}'",
        }

    questions: list[AppQuestion] = []
    by_question_id: dict[str, AppQuestion] = {}
    total_autofilled = 0
    total_fields = 0
    seen_fields: set[str] = set()

    state = get_app_state(case_id, program)
    existing_answers = state.answers if state else {}

    for form_id in form_ids:
        result = resolve_fields(form_id, profile)
        resolved = result.get("resolved", {})
        needs = result.get("needs_user_input", [])
        missing = result.get("missing", [])

        total_autofilled += len(resolved)
        # Prefer the real AcroForm field count as the honest denominator; fall back to
        # the curated schema counts when the PDF has no template on disk.
        discovered = discover_fields(form_id)
        total_fields += len(discovered) if discovered else (
            len(resolved) + len(needs) + len(missing)
        )

        askable = {q.get("field", "") for q in needs} - {""}
        grouped, covered = group_questions(form_id, profile, askable)
        for question in grouped:
            seen_fields |= set(question.fields)
            if question.field_id in existing_answers:
                continue
            # Group ids are shared across forms, so one fact asked by two forms in the
            # same program becomes a single question that fills both.
            already = by_question_id.get(question.field_id)
            if already is not None:
                merge_question(already, question)
                continue
            by_question_id[question.field_id] = question
            questions.append(question)

        info_by_field = field_index(form_id)
        for q in needs:
            field = q.get("field", "")
            if not field or field in covered or field in seen_fields:
                continue
            if field in existing_answers:
                continue
            seen_fields.add(field)
            loose = build_question(
                field_name=field,
                label=q.get("label", field),
                spec_type=q.get("type", "text"),
                form_id=form_id,
                info=info_by_field.get(field),
            )
            # A box no group claimed still asks something, and the something is often
            # a question already on screen: the form reprints the applicant's middle
            # name beside a section it belongs to.
            asked = same_fact(loose, questions)
            if asked is not None:
                merge_question(asked, loose)
                continue
            questions.append(loose)

    if state is None:
        state = ApplicationState(
            case_id=case_id,
            program=program,
            status=AppStatus.in_progress,
        )
    else:
        state.status = AppStatus.in_progress
    state.questions = questions
    save_app_state(state)

    return {
        "program": program,
        "form_ids": form_ids,
        "autofilled": total_autofilled,
        "total_fields": total_fields,
        "questions": [q.model_dump() for q in questions],
    }


def submit_answers(
    case_id: str, program: str, answers: dict[str, Any], profile: CaseProfile
) -> bytes:
    """Accept answers for missing fields, fill all forms, stitch into one PDF."""
    state = get_app_state(case_id, program)
    if state is None:
        state = ApplicationState(case_id=case_id, program=program)
    state.answers.update(answers)
    save_app_state(state)

    questions_by_id = {q.field_id: q for q in state.questions}
    form_ids = get_program_forms(program)
    filled_pdfs: list[bytes] = []

    for form_id in form_ids:
        result = resolve_fields(form_id, profile)
        merged_values = dict(result.get("resolved", {}))

        form_fields = set(load_schema(form_id).get("fields") or {})
        for field_id, raw in state.answers.items():
            question = questions_by_id.get(field_id)
            if question is not None:
                if question.group_id:
                    # One answer, several boxes with different values: the group decides
                    # which. Names are form-specific, so only this form's are written.
                    for target, value in grouped_values(question, raw).items():
                        if target in form_fields:
                            merged_values[target] = value
                    continue
                if question.form_id and question.form_id != form_id:
                    continue
                pdf_value = to_pdf_value(question, raw)
                if pdf_value is None:
                    continue
                for target in question.fields or [field_id]:
                    merged_values[target] = pdf_value
            elif isinstance(raw, str) and raw:
                # Legacy: answer keyed directly by PDF field name.
                merged_values[field_id] = raw

        try:
            pdf_bytes = write_values(form_id, merged_values)
            filled_pdfs.append(pdf_bytes)
        except FileNotFoundError:
            continue

    return stitch_pdfs(filled_pdfs)


def stitch_pdfs(pdf_bytes_list: list[bytes]) -> bytes:
    """Merge multiple PDF byte arrays into a single combined PDF."""
    writer = PdfWriter()
    for pdf_data in pdf_bytes_list:
        reader_stream = io.BytesIO(pdf_data)
        writer.append(reader_stream)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def complete_application(case_id: str, program: str) -> None:
    """Mark an application as completed."""
    state = get_app_state(case_id, program)
    if state is None:
        state = ApplicationState(case_id=case_id, program=program)
    state.status = AppStatus.completed
    save_app_state(state)
