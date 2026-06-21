"""Form filling + stitching.

Each program form has a field-map JSON (data/form_schemas/<program>.json) mapping PDF
field names to CaseProfile paths. `resolve_fields` computes values from the profile and
reports which fields still need to be asked. `fill_pdf` / `stitch` are thin wrappers over
fillpdf/pypdf — drop the fillable government PDFs into data/program_docs to enable them.
"""

import json
import os
from typing import Any

from ..models import CaseProfile

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "form_schemas")


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


def load_schema(program: str) -> dict[str, str]:
    path = os.path.join(SCHEMA_DIR, f"{program}.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def resolve_fields(program: str, profile: CaseProfile) -> dict[str, Any]:
    """Return {pdf_field: value, ...} plus a list of unresolved fields."""
    schema = load_schema(program)
    resolved: dict[str, Any] = {}
    missing: list[str] = []
    for pdf_field, profile_path in schema.items():
        value = _dig(profile, profile_path)
        if value in (None, "", []):
            missing.append(pdf_field)
        else:
            resolved[pdf_field] = value
    return {"resolved": resolved, "missing": missing}


def fill_pdf(template_path: str, output_path: str, values: dict[str, Any]) -> str:
    from fillpdf import fillpdfs

    fillpdfs.write_fillable_pdf(template_path, output_path, values)
    return output_path


def stitch(pdf_paths: list[str], output_path: str) -> str:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for p in pdf_paths:
        writer.append(p)
    with open(output_path, "wb") as fh:
        writer.write(fh)
    return output_path
