"""Application completion engine.

Manages the lifecycle of benefit applications: program->form-set mapping,
application status persistence (Postgres), autofill + Q&A resolution,
and stitching multiple filled PDFs into a single combined document.
"""

import io
from typing import Any

from pypdf import PdfWriter

from app.forms.discovery import discover_fields, field_index
from app.forms.filler import load_schema, pdf_path, resolve_fields, write_values
from app.applications.questions import (build_question, group_questions, grouped_values, merge_question, same_fact,
                                         to_pdf_value)
from app.applications.profile_facts import fact_questions, fact_value, is_fact, program_facts
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


PROGRAM_ALIASES = {
    "ihss": "IHSS",
    "in-home supportive services": "IHSS",
    "medical": "Medi-Cal",
    "medi cal": "Medi-Cal",
    "medi-cal": "Medi-Cal",
    "medicaid": "Medi-Cal",
    "va": "VA Caregiver Support",
    "va caregiver support": "VA Caregiver Support",
    "pfl": "Paid Family Leave",
    "medicare": "Medicare",
    "tax": "Caregiver Tax Relief",
}


def canonical_program(program: str) -> str:
    return PROGRAM_ALIASES.get(program.strip().casefold(), program.strip())


def get_program_forms(program: str) -> list[str]:
    forms = PROGRAM_FORMS.get(canonical_program(program), [])
    return list(forms) if all(pdf_path(form) for form in forms) else []


def program_is_active(profile: CaseProfile, program: str) -> bool:
    recipient = profile.care_recipient
    coverage = set(recipient.health_coverage)
    if program == "Medi-Cal" and (
        recipient.medicaid_status == "Enrolled now" or recipient.insurance == "medi-cal"
        or coverage.intersection({"Medicaid", "Medi-Cal", "Both Medicare and Medicaid"})
    ):
        return True
    if program == "Medicare" and (
        recipient.insurance == "medicare" or coverage.intersection({"Medicare", "Both Medicare and Medicaid"})
    ):
        return True
    statuses = profile.answers.get("recipient.program_statuses")
    return isinstance(statuses, dict) and any(
        (canonical_program(name) == program or program == "Medi-Cal" and name == "Medi-Cal care services or waiver")
        and status in ("Currently receiving benefits", "Renewal due", "Approved, awaiting services")
        for name, status in statuses.items()
    )


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
    """Start or resume an application: autofill all forms and return the questions to review.

    - Personal details the forms read from the profile come first, prefilled and editable
    - Questions answered on an earlier visit come back with their saved answers
    - Questions answered on another program's application come back as `profile_answers`"""
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

    facts = program_facts(form_ids, profile)
    questions: list[AppQuestion] = fact_questions(facts)
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
            asked = same_fact(loose, [q for q in questions if not is_fact(q.field_id)])
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
    elif state.status == AppStatus.open:
        state.status = AppStatus.in_progress
    # Saved answers whose question is no longer asked keep their field mappings.
    asked_ids = {q.field_id for q in questions}
    state.questions = [
        q for q in state.questions if q.field_id in existing_answers and q.field_id not in asked_ids
    ] + questions
    save_app_state(state)

    answers = {q.field_id: existing_answers[q.field_id] for q in questions
               if q.field_id in existing_answers and not is_fact(q.field_id)}
    shared = {fact: fact_value(profile, fact) for fact in facts}
    shared.update({q.field_id: profile.application_answers[q.field_id] for q in questions
                   if q.field_id in profile.application_answers and _fits(q, profile.application_answers[q.field_id])})
    return {
        "program": program,
        "form_ids": form_ids,
        "autofilled": total_autofilled,
        "total_fields": total_fields,
        "questions": [q.model_dump() for q in questions],
        "answers": answers,
        "profile_answers": {k: v for k, v in shared.items() if v not in (None, "", []) and k not in answers},
    }


def _fits(question: AppQuestion, value: Any) -> bool:
    """Whether another form's answer is a valid answer here: a choice must be one of these options."""
    if not question.options or question.type not in ("single_select", "multi_select"):
        return True
    chosen = value if isinstance(value, list) else [value]
    return all(c in question.options for c in chosen)


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
            if is_fact(field_id):
                continue  # read from the profile by resolve_fields
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


def complete_application(case_id: str, program: str) -> AppStatus:
    """Mark an application as completed."""
    state = get_app_state(case_id, program)
    if state is None:
        state = ApplicationState(case_id=case_id, program=program)
    if state.status in (AppStatus.open, AppStatus.in_progress, AppStatus.needs_info):
        state.status = AppStatus.completed
        save_app_state(state)
    return state.status
