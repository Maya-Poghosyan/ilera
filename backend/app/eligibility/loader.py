"""Load ProgramPolicy models from the authored JSON in data/program_policies/.

The committed files are the single source of truth; they ship in the image.
"""

from __future__ import annotations

import json
import os
from functools import cache
from typing import Optional

from .policy import ProgramPolicy

_SEED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "program_policies")


@cache
def _policies() -> dict[str, ProgramPolicy]:
    out: dict[str, ProgramPolicy] = {}
    for fname in sorted(os.listdir(_SEED_DIR)):
        if fname.endswith(".json"):
            with open(os.path.join(_SEED_DIR, fname), encoding="utf-8") as fh:
                policy = ProgramPolicy.model_validate(json.load(fh))
            out[policy.program_id] = policy
    return out


def get_policy(program_id: str) -> Optional[ProgramPolicy]:
    policy = _policies().get(program_id)
    return policy.model_copy(deep=True) if policy else None


def list_policies() -> list[ProgramPolicy]:
    return [p.model_copy(deep=True) for p in _policies().values()]
