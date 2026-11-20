"""Form filling engine.

Loads field-map schemas from data/form_schemas/<form_id>.json, resolves values from a
CaseProfile, and writes them into the fillable PDF templates under data/forms/ (shipped in
the image; the single source for discovery, filling and authoring) using pypdf.
"""

from __future__ import annotations

import io
import os
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

from app.cases.models import CaseProfile
from app.forms.schema_store import all_schemas, load_schema

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
    for data in all_schemas():
        meta = data.get("_meta", {})
        fields = data.get("fields", {})
        mapped_count = sum(1 for f in fields.values() if f.get("profile_path"))
        total_in_map = len(fields)
        schemas.append({
            "form_id": meta.get("form_id", ""),
            "title": meta.get("title", ""),
            "program": meta.get("program", ""),
            "agency": meta.get("agency", ""),
            "source_url": meta.get("source_url", ""),
            "pdf_path": meta.get("pdf_path", ""),
            "total_pdf_fields": meta.get("total_fields", 0),
            "mapped_fields": mapped_count,
            "total_schema_fields": total_in_map,
        })
    return sorted(schemas, key=lambda s: s["form_id"])


def resolve_fields(form_id: str, profile: CaseProfile) -> dict[str, Any]:
    """Return resolved field values and lists of missing/needs_user_input fields."""
    schema = load_schema(form_id)
    fields_map = schema.get("fields", {})

    resolved: dict[str, Any] = {}
    missing: list[str] = []
    needs_user_input: list[dict] = []

    for pdf_field, spec in fields_map.items():
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

        if spec.get("format") == "date" and isinstance(value, str) and value:
            from datetime import date
            try:
                value = date.fromisoformat(value).strftime("%m/%d/%Y")
            except ValueError:
                pass

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


def pdf_path(form_id: str) -> str | None:
    """The form's PDF template, or None when the form has none."""
    pdf_rel = load_schema(form_id).get("_meta", {}).get("pdf_path", "")
    full = os.path.join(FORMS_DIR, pdf_rel) if pdf_rel else ""
    return full if full and os.path.exists(full) else None


def write_values(form_id: str, values: dict[str, Any]) -> bytes:
    """The form's PDF with `values` written into its AcroForm fields."""
    path = pdf_path(form_id)
    if path is None:
        raise FileNotFoundError(f"No PDF template found for form {form_id}")
    writer = PdfWriter()
    writer.append(PdfReader(path))  # append preserves the AcroForm structure
    acroform_ref = writer._root_object.get(NameObject("/AcroForm"))
    if acroform_ref is not None:
        acroform = acroform_ref.get_object() if hasattr(acroform_ref, "get_object") else acroform_ref
        # Viewers render the filled values instead of stale appearance streams.
        acroform[NameObject("/NeedAppearances")] = BooleanObject(True)
    for page in writer.pages:
        writer.update_page_form_field_values(page, values)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def fill_pdf(form_id: str, profile: CaseProfile) -> bytes:
    """The form filled from a CaseProfile."""
    return write_values(form_id, resolve_fields(form_id, profile)["resolved"])
