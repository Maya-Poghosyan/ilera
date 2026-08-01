"""AcroForm field extraction utility.

Usage:
    python -m app.forms.extract <pdf_path>

Lists every fillable field name, type (text/checkbox/radio/choice), and tooltip.
"""

import json
import sys
from typing import Any

from pypdf import PdfReader


FIELD_TYPE_MAP = {
    "/Tx": "text",
    "/Btn": "checkbox",
    "/Ch": "choice",
    "/Sig": "signature",
}


def extract_fields(pdf_path: str) -> list[dict]:
    reader = PdfReader(pdf_path)
    fields = reader.get_fields()
    if not fields:
        return []

    result: list[dict] = []
    for name, field in fields.items():
        ft = str(field.get("/FT", ""))
        field_type = FIELD_TYPE_MAP.get(ft, "unknown")

        # Distinguish radio buttons from checkboxes
        if ft == "/Btn":
            flags = field.get("/Ff", 0)
            if isinstance(flags, int) and flags & (1 << 15):
                field_type = "radio"
            opts = field.get("/Opt")
            if opts:
                field_type = "radio"

        entry: dict = {
            "name": name,
            "type": field_type,
        }

        tooltip = field.get("/TU", "")
        if tooltip:
            entry["tooltip"] = str(tooltip)

        opts = field.get("/Opt")
        if opts:
            entry["options"] = [str(o) for o in opts]

        result.append(entry)

    return result


def _qualified_name(annot: Any) -> str | None:
    """Fully qualified field name of a widget, matching ``PdfReader.get_fields`` keys.

    A widget annotation often carries only the leaf ``/T``; the rest of the name comes
    from its ``/Parent`` chain. Widgets merged into their field node have no ``/T`` of
    their own and inherit the parent's name outright.
    """
    parts: list[str] = []
    node = annot
    seen: set[int] = set()
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        title = node.get("/T")
        if title is not None:
            parts.append(str(title))
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
    if not parts:
        return None
    return ".".join(reversed(parts))


def extract_pages(pdf_path: str) -> list[dict]:
    """Per page: the printed text and the fields whose widgets sit on it.

    ``extract_fields`` only sees the AcroForm layer, which has no page text and often
    no usable label. Pairing the two lets a reader line an opaque field name up with
    the question actually printed next to it.
    """
    reader = PdfReader(pdf_path)
    pages: list[dict] = []
    for number, page in enumerate(reader.pages, start=1):
        names: list[str] = []
        for ref in page.get("/Annots") or []:
            annot = ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue
            name = _qualified_name(annot)
            if name and name not in names:
                names.append(name)
        pages.append({
            "page": number,
            "text": page.extract_text() or "",
            "fields": names,
        })
    return pages


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m app.forms.extract <pdf_path>", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    fields = extract_fields(pdf_path)
    print(json.dumps(fields, indent=2, ensure_ascii=False))
    print(f"\nTotal fields: {len(fields)}", file=sys.stderr)


if __name__ == "__main__":
    main()
