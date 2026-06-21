"""Form filling engine.

Loads field-map schemas from data/form_schemas/<form_id>.json, resolves values
from a CaseProfile, and writes them into fillable PDF AcroForms using pypdf.
"""

import io
import json
import os
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

from ..models import CaseProfile

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "form_schemas")
FORMS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "forms")


def _dig(obj: Any, path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
        if cur is None:
            return None
    return cur


def _transform(value: Any, transform: str) -> Any:
    if transform == "join_list" and isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if transform == "hours_weekly_to_monthly" and isinstance(value, (int, float)):
        return str(round(value * 4.33))
    return value


def list_schemas() -> list[dict]:
    """Return metadata for all available form schemas."""
    schemas: list[dict] = []
    if not os.path.isdir(SCHEMA_DIR):
        return schemas
    for fname in sorted(os.listdir(SCHEMA_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(SCHEMA_DIR, fname)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        meta = data.get("_meta", {})
        fields = data.get("fields", {})
        mapped_count = sum(1 for f in fields.values() if f.get("profile_path"))
        total_in_map = len(fields)
        schemas.append({
            "form_id": meta.get("form_id", fname.replace(".json", "")),
            "title": meta.get("title", ""),
            "program": meta.get("program", ""),
            "agency": meta.get("agency", ""),
            "source_url": meta.get("source_url", ""),
            "pdf_path": meta.get("pdf_path", ""),
            "total_pdf_fields": meta.get("total_fields", 0),
            "mapped_fields": mapped_count,
            "total_schema_fields": total_in_map,
        })
    return schemas


def load_schema(form_id: str) -> dict:
    """Load a field-map schema by form_id (case-insensitive)."""
    path = os.path.join(SCHEMA_DIR, f"{form_id.lower()}.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def resolve_fields(form_id: str, profile: CaseProfile) -> dict[str, Any]:
    """Return resolved field values and lists of missing/needs_user_input fields."""
    schema = load_schema(form_id)
    fields_map = schema.get("fields", {})
    if not fields_map:
        # Fall back to legacy flat schema (form_id -> profile_path)
        fields_map = {k: v for k, v in schema.items() if k != "_meta"}
        if fields_map:
            return _resolve_legacy(fields_map, profile)

    resolved: dict[str, Any] = {}
    missing: list[str] = []
    needs_user_input: list[dict] = []

    for pdf_field, spec in fields_map.items():
        if isinstance(spec, str):
            # Legacy format: direct profile_path string
            value = _dig(profile, spec)
            if value in (None, "", []):
                missing.append(pdf_field)
            else:
                resolved[pdf_field] = value
            continue

        profile_path = spec.get("profile_path")
        label = spec.get("label", pdf_field)
        field_type = spec.get("type", "text")

        if spec.get("needs_user_input") and not profile_path:
            needs_user_input.append({"field": pdf_field, "label": label, "type": field_type})
            continue

        if not profile_path:
            needs_user_input.append({"field": pdf_field, "label": label, "type": field_type})
            continue

        value = _dig(profile, profile_path)

        if value in (None, "", []):
            if spec.get("needs_user_input"):
                needs_user_input.append({"field": pdf_field, "label": label, "type": field_type})
            else:
                missing.append(pdf_field)
            continue

        transform = spec.get("transform")
        if transform:
            value = _transform(value, transform)

        # Handle checkbox fields with check_when
        if field_type == "checkbox" and "check_when" in spec:
            check_when = spec["check_when"]
            if value == check_when:
                resolved[pdf_field] = "/Yes"
            continue

        # Handle radio/checkbox with value_map
        value_map = spec.get("value_map")
        if value_map and isinstance(value_map, dict):
            mapped = value_map.get(str(value))
            if mapped is not None:
                resolved[pdf_field] = mapped
            else:
                resolved[pdf_field] = str(value)
            continue

        if isinstance(value, bool):
            resolved[pdf_field] = "/Yes" if value else "/Off"
        elif isinstance(value, list):
            resolved[pdf_field] = ", ".join(str(v) for v in value)
        else:
            resolved[pdf_field] = str(value)

    return {
        "resolved": resolved,
        "missing": missing,
        "needs_user_input": needs_user_input,
    }


def _resolve_legacy(fields_map: dict[str, str], profile: CaseProfile) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    missing: list[str] = []
    for pdf_field, profile_path in fields_map.items():
        value = _dig(profile, profile_path)
        if value in (None, "", []):
            missing.append(pdf_field)
        else:
            resolved[pdf_field] = value
    return {"resolved": resolved, "missing": missing, "needs_user_input": []}


def _get_pdf_path(form_id: str) -> str | None:
    schema = load_schema(form_id)
    meta = schema.get("_meta", {})
    pdf_rel = meta.get("pdf_path", "")
    if pdf_rel:
        full = os.path.join(FORMS_DIR, pdf_rel)
        if os.path.exists(full):
            return full
    return None


def fill_pdf(form_id: str, profile: CaseProfile) -> bytes:
    """Fill a PDF template with resolved CaseProfile values and return PDF bytes."""
    pdf_path = _get_pdf_path(form_id)
    if not pdf_path:
        raise FileNotFoundError(f"No PDF template found for form {form_id}")

    result = resolve_fields(form_id, profile)
    values = result["resolved"]

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    # Clone via append to preserve AcroForm structure
    writer.append(reader)

    # Set NeedAppearances so PDF viewers render filled values
    acroform_ref = writer._root_object.get(NameObject("/AcroForm"))
    if acroform_ref is not None:
        acroform = acroform_ref.get_object() if hasattr(acroform_ref, "get_object") else acroform_ref
        acroform[NameObject("/NeedAppearances")] = BooleanObject(True)

    # Write values into form fields
    for page in writer.pages:
        writer.update_page_form_field_values(page, values)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def stitch(pdf_paths: list[str], output_path: str) -> str:
    writer = PdfWriter()
    for p in pdf_paths:
        writer.append(p)
    with open(output_path, "wb") as fh:
        writer.write(fh)
    return output_path
