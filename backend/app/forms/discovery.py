"""Authoritative form-field discovery.

`resolve_fields` (filler.py) trusts the hand-authored ``form_schemas/*.json`` overlay
for *which fields exist*. That overlay is sparse and can drift. This module reads the
ground truth straight from each PDF's AcroForm via ``extract_fields`` so the rest of the
application flow (autofill, question composition, the curated-key validation test) works
from the real field inventory instead of a static guess.
"""

from dataclasses import dataclass, field

from .extract import extract_fields
from .filler import _get_pdf_path

# Accessibility artifacts that carry a fillable field but are not real data inputs.
# Government PDFs annotate screen-reader helpers with these phrases in the tooltip (/TU).
_JUNK_TOOLTIP_MARKERS = (
    "forms mode",
    "created to be accessible",
)

# PDF AcroForm field type -> intake QuestionField FieldType.
_PDF_TYPE_TO_INTAKE = {
    "text": "short_text",
    "checkbox": "boolean",
    "radio": "single_select",
    "choice": "single_select",
}


@dataclass
class FieldInfo:
    """A single fillable field as it actually exists in the PDF."""

    name: str
    pdf_type: str
    tooltip: str = ""
    options: list[str] = field(default_factory=list)

    @property
    def intake_type(self) -> str:
        """The frontend QuestionField type this PDF field maps to."""
        return _PDF_TYPE_TO_INTAKE.get(self.pdf_type, "short_text")


def _clean(text) -> str:
    """Collapse whitespace/carriage returns that AcroForm labels often carry."""
    return " ".join(str(text or "").split())


def is_junk(entry: dict) -> bool:
    """True for a fillable field that is not a data input (signature or a11y artifact)."""
    if entry.get("type") == "signature":
        return True
    tooltip = (entry.get("tooltip") or "").lower()
    return any(marker in tooltip for marker in _JUNK_TOOLTIP_MARKERS)


def discover_fields(form_id: str) -> list[FieldInfo]:
    """Return the real, fillable data fields for a form (junk/signature removed).

    Returns an empty list when the form has no PDF template on disk.
    """
    pdf_path = _get_pdf_path(form_id)
    if not pdf_path:
        return []
    fields: list[FieldInfo] = []
    for entry in extract_fields(pdf_path):
        if is_junk(entry):
            continue
        fields.append(
            FieldInfo(
                name=entry["name"],
                pdf_type=entry.get("type", "text"),
                tooltip=_clean(entry.get("tooltip", "")),
                options=[_clean(o) for o in entry.get("options", []) or []],
            )
        )
    return fields


def field_index(form_id: str) -> dict[str, FieldInfo]:
    """Real fields keyed by exact AcroForm field name."""
    return {f.name: f for f in discover_fields(form_id)}
