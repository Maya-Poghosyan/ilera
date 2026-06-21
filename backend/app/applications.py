"""Application completion engine.

Manages the lifecycle of benefit applications: program->form-set mapping,
application status persistence (Redis / in-memory), autofill + Q&A resolution,
and stitching multiple filled PDFs into a single combined document.
"""

import io
import json
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field
from pypdf import PdfWriter

from .config import get_settings
from .forms.filler import load_schema, resolve_fields
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


class ApplicationState(BaseModel):
    case_id: str
    program: str
    status: AppStatus = AppStatus.open
    answers: dict[str, str] = Field(default_factory=dict)


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


def start_application(
    case_id: str, program: str, profile: CaseProfile
) -> dict[str, Any]:
    """Start or resume an application: autofill all forms and compute missing fields."""
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

    all_resolved: dict[str, dict[str, Any]] = {}
    all_questions: list[dict[str, Any]] = []
    total_autofilled = 0
    total_fields = 0
    seen_labels: set[str] = set()

    state = get_app_state(case_id, program)
    existing_answers = state.answers if state else {}

    for form_id in form_ids:
        result = resolve_fields(form_id, profile)
        resolved = result.get("resolved", {})
        needs = result.get("needs_user_input", [])
        missing = result.get("missing", [])

        all_resolved[form_id] = resolved
        total_autofilled += len(resolved)
        total_fields += len(resolved) + len(needs) + len(missing)

        for q in needs:
            label = q.get("label", q.get("field", ""))
            if label in seen_labels:
                continue
            seen_labels.add(label)
            field = q.get("field", "")
            if field in existing_answers:
                continue
            all_questions.append({
                "field": field,
                "label": label,
                "type": q.get("type", "text"),
                "form_id": form_id,
            })

    if state is None:
        state = ApplicationState(
            case_id=case_id,
            program=program,
            status=AppStatus.in_progress,
        )
    else:
        state.status = AppStatus.in_progress
    save_app_state(state)

    return {
        "program": program,
        "form_ids": form_ids,
        "autofilled": total_autofilled,
        "total_fields": total_fields,
        "questions": all_questions,
    }


def submit_answers(
    case_id: str, program: str, answers: dict[str, str], profile: CaseProfile
) -> bytes:
    """Accept answers for missing fields, fill all forms, stitch into one PDF."""
    state = get_app_state(case_id, program)
    if state is None:
        state = ApplicationState(case_id=case_id, program=program)
    state.answers.update(answers)
    save_app_state(state)

    form_ids = get_program_forms(program)
    filled_pdfs: list[bytes] = []

    for form_id in form_ids:
        result = resolve_fields(form_id, profile)
        merged_values = dict(result.get("resolved", {}))

        schema = load_schema(form_id)
        fields_map = schema.get("fields", {})
        for pdf_field, spec in fields_map.items():
            if not isinstance(spec, dict):
                continue
            label = spec.get("label", pdf_field)
            if pdf_field in state.answers:
                merged_values[pdf_field] = state.answers[pdf_field]
            elif label in state.answers:
                merged_values[pdf_field] = state.answers[label]

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
