"""AcroForm field extraction utility.

Usage:
    python -m app.forms.extract <pdf_path>

Lists every fillable field name, type (text/checkbox/radio/choice), and tooltip.
"""

import json
import sys

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
