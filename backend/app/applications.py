"""Application completion engine.

Manages the lifecycle of benefit applications: program->form-set mapping,
application status persistence (Redis / in-memory), autofill + Q&A resolution,
and stitching multiple filled PDFs into a single combined document.
"""

import io
import json
import re
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field
from pypdf import PdfWriter

from .config import get_settings
from .forms.discovery import discover_fields, field_index
from .forms.filler import load_schema, resolve_fields
from .forms.groups import (
    GroupInput,
    applies,
    is_profile_path,
    load_groups,
    load_skips,
    parse_condition,
    pdf_values,
)
from .models import CaseProfile

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
# Application status model + persistence
# ---------------------------------------------------------------------------


class AppStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    needs_info = "needs_info"
    completed = "completed"


class AppQuestion(BaseModel):
    """A single question shown one-by-one on the frontend.

    The top-level fields (``field_id``, ``text``, ``type``, ``required``, ``options``,
    ``why_this_matters``) are the intake ``QuestionField`` shape, so the frontend renders
    these directly with no adapter. The remaining fields are backend-only metadata used to
    translate the user's answer back into concrete PDF values at fill time (and, later, to
    feed the specialist layer).
    """

    field_id: str
    text: str
    type: str = "short_text"
    required: bool = True
    options: list[str] = Field(default_factory=list)
    why_this_matters: str = ""

    # backend-only
    form_id: str = ""
    fields: list[str] = Field(default_factory=list)
    option_values: dict[str, str] = Field(default_factory=dict)  # option label -> raw PDF value
    interpret: bool = False

    # Questions sharing a ``group_id`` are one screen: a group asks for one real-world
    # fact and each of its inputs fills different boxes, so they are answered together.
    group_id: str = ""
    group_prompt: str = ""
    input: str = ""
    option_fields: dict[str, list[str]] = Field(default_factory=dict)
    # A "if yes, ..." follow-up: only shown once an earlier answer satisfies this, e.g.
    # `past_ihss.received_ihss_before == "Yes"`. Conditions the profile can settle are
    # applied here instead, and the group never reaches the frontend at all.
    ask_when: str = ""


class ApplicationState(BaseModel):
    case_id: str
    program: str
    status: AppStatus = AppStatus.open
    answers: dict[str, Any] = Field(default_factory=dict)
    questions: list[AppQuestion] = Field(default_factory=list)


_memory: dict[str, str] = {}
_REDIS_PREFIX = "ilera:app:"


def _redis():
    settings = get_settings()
    if not settings.has_redis:
        return None
    import redis

    return redis.from_url(settings.redis_url, decode_responses=True)


def _key(case_id: str, program: str) -> str:
    slug = program.lower().replace(" ", "_").replace("/", "_")
    return f"{_REDIS_PREFIX}{case_id}:{slug}"


def _mem_key(case_id: str, program: str) -> str:
    slug = program.lower().replace(" ", "_").replace("/", "_")
    return f"{case_id}:{slug}"


def save_app_state(state: ApplicationState) -> None:
    payload = state.model_dump_json()
    client = _redis()
    if client is not None:
        client.set(_key(state.case_id, state.program), payload)
    else:
        _memory[_mem_key(state.case_id, state.program)] = payload


def get_app_state(case_id: str, program: str) -> Optional[ApplicationState]:
    client = _redis()
    k = _key(case_id, program) if client is not None else _mem_key(case_id, program)
    raw = client.get(k) if client is not None else _memory.get(k)
    if not raw:
        return None
    return ApplicationState.model_validate(json.loads(raw))


def list_app_states(case_id: str) -> list[ApplicationState]:
    client = _redis()
    if client is not None:
        pattern = f"{_REDIS_PREFIX}{case_id}:*"
        keys = client.keys(pattern)
        if not keys:
            return []
        pipe = client.pipeline()
        for k in keys:
            pipe.get(k)
        results = pipe.execute()
        return [ApplicationState.model_validate(json.loads(r)) for r in results if r]
    prefix = f"{case_id}:"
    return [
        ApplicationState.model_validate(json.loads(v))
        for k, v in _memory.items()
        if k.startswith(prefix)
    ]


# ---------------------------------------------------------------------------
# Application flow logic
# ---------------------------------------------------------------------------


def _clean_label(text: str) -> str:
    """Trim a form label/tooltip down to a readable question prompt."""
    text = " ".join((text or "").split())
    # Drop a leading "Section 1 – ..." style prefix, keeping the field's own label.
    for sep in (". ", " - ", " \u2013 "):
        if sep in text and text.lower().startswith("section"):
            text = text.split(sep, 1)[1]
            break
    # The frontend marks optional fields itself, so a label saying so reads twice.
    text = re.sub(r"[\s(]*\(?optional\)?[\s)]*$", "", text, flags=re.I)
    return text.strip()


def _build_question(
    field_name: str, label: str, spec_type: str, form_id: str, info
) -> AppQuestion:
    """Compose a single AppQuestion, enriched with the real PDF field type/options."""
    if info is not None:
        qtype = info.intake_type
        options = list(info.options)
    else:
        qtype = _SPEC_TYPE_TO_INTAKE.get(spec_type, "short_text")
        options = []
    return AppQuestion(
        field_id=field_name,
        text=_clean_label(label) or field_name,
        type=qtype,
        required=True,
        options=options,
        form_id=form_id,
        fields=[field_name],
        option_values={o: o for o in options},
    )


# Fallback map when a field isn't found in the real PDF (schema spec type -> intake type).
_SPEC_TYPE_TO_INTAKE = {
    "text": "short_text",
    "checkbox": "boolean",
    "radio": "single_select",
    "choice": "single_select",
    "date": "short_text",
}


def _group_questions(
    form_id: str, profile: CaseProfile, askable: set[str]
) -> tuple[list[AppQuestion], set[str]]:
    """Questions from a form's committed groups, and the fields they account for.

    A group that can't apply to this profile — a second household member's details for a
    one-person household — is dropped whole, so none of its boxes are ever mentioned.
    Fields the group pass marked office-use are accounted for without being asked.
    """
    schema = load_schema(form_id)
    covered: set[str] = set(load_skips(schema))
    questions: list[AppQuestion] = []

    for group in load_groups(schema):
        targets = {f for f in group.target_fields() if f in askable}
        if not targets:
            continue
        covered |= targets
        if not applies(group, profile):
            continue
        parsed = parse_condition(group.applies_when or "")
        ask_when = (
            group.applies_when
            if parsed and not is_profile_path(parsed[0])
            else ""
        )
        for inp in group.inputs:
            questions.append(
                AppQuestion(
                    field_id=f"{group.id}.{inp.key}",
                    text=_clean_label(inp.label),
                    type=inp.type,
                    required=inp.required,
                    options=list(inp.options),
                    why_this_matters=inp.help or group.help,
                    form_id=form_id,
                    fields=list(inp.fields),
                    option_values=dict(inp.option_values),
                    option_fields={k: list(v) for k, v in inp.option_fields.items()},
                    group_id=group.id,
                    group_prompt=group.prompt,
                    input=inp.key,
                    ask_when=ask_when,
                )
            )
    return questions, covered


def _merge_question(existing: AppQuestion, addition: AppQuestion) -> None:
    """Fold a second form's copy of the same question into the one already asked."""
    existing.fields = list(dict.fromkeys([*existing.fields, *addition.fields]))
    for label, names in addition.option_fields.items():
        merged = [*existing.option_fields.get(label, []), *names]
        existing.option_fields[label] = list(dict.fromkeys(merged))
    existing.option_values.update(addition.option_values)
    for label in addition.options:
        if label not in existing.options:
            existing.options.append(label)
    if existing.form_id != addition.form_id:
        existing.form_id = ""  # it now fills more than one form


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
        grouped, covered = _group_questions(form_id, profile, askable)
        for question in grouped:
            seen_fields |= set(question.fields)
            if question.field_id in existing_answers:
                continue
            # Group ids are shared across forms, so one fact asked by two forms in the
            # same program becomes a single question that fills both.
            already = by_question_id.get(question.field_id)
            if already is not None:
                _merge_question(already, question)
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
            questions.append(
                _build_question(
                    field_name=field,
                    label=q.get("label", field),
                    spec_type=q.get("type", "text"),
                    form_id=form_id,
                    info=info_by_field.get(field),
                )
            )

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


def _to_pdf_value(question: AppQuestion, raw: Any) -> Optional[str]:
    """Translate a user's answer into the concrete AcroForm value pypdf expects."""
    if raw is None or raw == "" or raw == []:
        return None
    if question.type == "boolean":
        truthy = raw is True or str(raw).strip().lower() in ("true", "yes", "1")
        return "/Yes" if truthy else "/Off"
    if question.type in ("single_select", "multi_select"):
        if isinstance(raw, list):
            return ", ".join(question.option_values.get(str(v), str(v)) for v in raw)
        return question.option_values.get(str(raw), str(raw))
    return str(raw)


def _grouped_values(question: AppQuestion, raw: Any) -> dict[str, str]:
    """Where a grouped answer lands, using the split declared when the group was drafted."""
    return pdf_values(
        GroupInput(
            key=question.input or question.field_id,
            label=question.text,
            type=question.type,
            fields=question.fields,
            options=question.options,
            option_fields=question.option_fields,
            option_values=question.option_values,
        ),
        raw,
    )


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
                    for target, value in _grouped_values(question, raw).items():
                        if target in form_fields:
                            merged_values[target] = value
                    continue
                if question.form_id and question.form_id != form_id:
                    continue
                pdf_value = _to_pdf_value(question, raw)
                if pdf_value is None:
                    continue
                for target in question.fields or [field_id]:
                    merged_values[target] = pdf_value
            elif isinstance(raw, str) and raw:
                # Legacy: answer keyed directly by PDF field name.
                merged_values[field_id] = raw

        try:
            pdf_bytes = _fill_pdf_with_overrides(form_id, merged_values)
            filled_pdfs.append(pdf_bytes)
        except FileNotFoundError:
            continue

    return stitch_pdfs(filled_pdfs)


def _fill_pdf_with_overrides(form_id: str, values: dict[str, str]) -> bytes:
    """Fill a PDF with explicit field values (bypassing CaseProfile resolution)."""
    from pypdf import PdfReader

    from .forms.filler import _get_pdf_path

    from pypdf.generic import BooleanObject, NameObject

    pdf_path = _get_pdf_path(form_id)
    if not pdf_path:
        raise FileNotFoundError(f"No PDF template found for form {form_id}")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    writer.append(reader)

    acroform_ref = writer._root_object.get(NameObject("/AcroForm"))
    if acroform_ref is not None:
        acroform = (
            acroform_ref.get_object()
            if hasattr(acroform_ref, "get_object")
            else acroform_ref
        )
        acroform[NameObject("/NeedAppearances")] = BooleanObject(True)

    for page in writer.pages:
        writer.update_page_form_field_values(page, values)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


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
