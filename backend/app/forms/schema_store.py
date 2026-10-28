"""Load form field-map schemas from the `reference.form_schemas` table.

Authored reference data: one row per form, the same JSON shape as
data/form_schemas/<form_id>.json ({_meta, fields}). Read path is DB-first with a
file-seed fallback, mirroring the eligibility policy loader — so the app still fills
forms with zero services, and the committed JSON remains the source that seeds the DB.

Only the SOURCE of the schema moves here. The profile_path field-map contract that
filler.resolve_fields depends on is unchanged.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from .. import db

logger = logging.getLogger("ilera.forms.schema_store")

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "form_schemas")

_store = db.JsonStore("form_schemas", keys=("form_id",), schema="reference")


def _iter_seed_files() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    if not os.path.isdir(SCHEMA_DIR):
        return out
    for fname in sorted(os.listdir(SCHEMA_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(SCHEMA_DIR, fname), encoding="utf-8") as fh:
            doc = json.load(fh)
        form_id = os.path.splitext(fname)[0].lower()
        out.append((form_id, doc))
    return out


def seed_form_schemas_from_files() -> int:
    """Upsert every bundled form schema into reference.form_schemas. Idempotent."""
    seeds = _iter_seed_files()
    for form_id, doc in seeds:
        _store.put(form_id, json.dumps(doc))
    if seeds:
        logger.info("Seeded %d form schemas into reference.form_schemas", len(seeds))
    return len(seeds)


def load_schema(form_id: str) -> dict:
    """One form's schema JSON, DB-first with a file-seed fallback. {} if unknown."""
    key = form_id.lower()
    doc = _store.get(key)
    if doc is not None:
        return doc
    for seed_id, seed in _iter_seed_files():
        if seed_id == key:
            return seed
    return {}


def all_schemas() -> list[dict]:
    """Every form schema JSON, DB-first with a file-seed fallback."""
    docs = _store.list()
    if docs:
        return docs
    return [seed for _, seed in _iter_seed_files()]
