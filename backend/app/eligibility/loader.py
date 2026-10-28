"""Load and persist ProgramPolicy models from the `reference.program_policies` table.

Read path: DB-first. If the reference table is empty (fresh database) or Postgres is
unconfigured, fall back to the bundled JSON seeds in data/program_policies/ — the same
file-fallback pattern the RAG index and other stores use, so the app still boots and
evaluates with zero services.

Seeding: `seed_policies_from_files()` loads the bundled JSON into the table and is
idempotent (upsert by program_id). Authored policy lives as JSON in the repo and is
promoted into Postgres; the files remain the source of truth that CI/migrations seed from.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from .. import db
from .policy import ProgramPolicy

logger = logging.getLogger("ilera.eligibility.policy")

_SEED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "program_policies")

# reference-schema store: (program_id PK, doc jsonb).
_store = db.JsonStore("program_policies", keys=("program_id",), schema="reference")


def _iter_seed_files() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    if not os.path.isdir(_SEED_DIR):
        return out
    for fname in sorted(os.listdir(_SEED_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(_SEED_DIR, fname), encoding="utf-8") as fh:
            doc = json.load(fh)
        pid = doc.get("program_id") or os.path.splitext(fname)[0]
        out.append((pid, doc))
    return out


def seed_policies_from_files() -> int:
    """Upsert every bundled policy JSON into reference.program_policies. Idempotent.

    Returns the number of policies written. Safe to call at startup or from a migration.
    """
    seeds = _iter_seed_files()
    for pid, doc in seeds:
        # Validate before persisting so a malformed seed fails loudly, not silently.
        policy = ProgramPolicy.model_validate(doc)
        _store.put(policy.program_id, policy.model_dump_json())
    if seeds:
        logger.info("Seeded %d program policies into reference.program_policies", len(seeds))
    return len(seeds)


def get_policy(program_id: str) -> Optional[ProgramPolicy]:
    """One program's policy, DB-first with a file-seed fallback."""
    doc = _store.get(program_id)
    if doc is None:
        # Fall back to the bundled seed (fresh DB / no DB).
        for pid, seed in _iter_seed_files():
            if pid == program_id:
                return ProgramPolicy.model_validate(seed)
        return None
    return ProgramPolicy.model_validate(doc)


def list_policies() -> list[ProgramPolicy]:
    """All program policies, DB-first with a file-seed fallback."""
    docs = _store.list()
    if docs:
        return [ProgramPolicy.model_validate(d) for d in docs]
    return [ProgramPolicy.model_validate(seed) for _, seed in _iter_seed_files()]
