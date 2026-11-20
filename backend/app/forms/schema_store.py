"""Load form field-map schemas from the authored JSON in data/form_schemas/.

One file per form ({_meta, fields}); the committed files are the single source of truth.
"""

from __future__ import annotations

import json
import os

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "form_schemas")


def _read(fname: str) -> dict:
    with open(os.path.join(SCHEMA_DIR, fname), encoding="utf-8") as fh:
        return json.load(fh)


def load_schema(form_id: str) -> dict:
    """One form's schema JSON (case-insensitive id). {} if unknown."""
    fname = f"{form_id.lower()}.json"
    return _read(fname) if os.path.isfile(os.path.join(SCHEMA_DIR, fname)) else {}


def all_schemas() -> list[dict]:
    return [_read(f) for f in sorted(os.listdir(SCHEMA_DIR)) if f.endswith(".json")]
