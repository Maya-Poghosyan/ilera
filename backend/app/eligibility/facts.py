"""Typed fact addresses and validated writes shared by eligibility and intake.

Legacy values without metadata remain unknown for eligibility. This intentionally
prevents CA/False defaults from acting as evidence. The API caller owns case access
and persistence; this module validates and updates one in-memory case atomically.
"""
from datetime import datetime, timezone
from typing import Any

from pydantic import TypeAdapter

from ..models import CaseProfile, Caregiver, CareRecipient, Household
from .fact_models import FactMetadata

_ROOTS = {"care_recipient": CareRecipient, "caregiver": Caregiver, "household": Household}
# In-memory-only values must never become persisted case facts or event payloads.
_EPHEMERAL = {"care_recipient.ssn"}


def fact_registry() -> dict[str, Any]:
    return {
        f"{root}.{name}": field.annotation
        for root, model in _ROOTS.items()
        for name, field in model.model_fields.items()
        if f"{root}.{name}" not in _EPHEMERAL
    }


def write_fact(
    profile: CaseProfile, path: str, value: Any, *,
    availability: str = "known", source_kind: str = "user_report",
    source_ref: str | None = None, precision: str = "exact",
) -> bool:
    """Validate before mutation; identical writes are no-ops. Unknown clears stale values."""
    registry = fact_registry()
    if path not in registry:
        raise ValueError(f"Unknown or nonpersistent fact path: {path}")
    root, name = path.split(".")
    model = _ROOTS[root]
    validated = (TypeAdapter(registry[path]).validate_python(value, strict=True)
                 if availability == "known" else model.model_fields[name].get_default(call_default_factory=True))
    non_answers = {"", "unknown", "i'm not sure", "prefer not to answer"}
    if availability == "known" and (
        validated is None
        or isinstance(validated, str) and validated.strip().lower() in non_answers
        or isinstance(validated, list) and any(isinstance(item, str) and item.strip().lower() in non_answers for item in validated)
    ):
        raise ValueError("A known fact must supply an actual answer")
    previous = profile.fact_metadata.get(path)
    metadata = FactMetadata(
        availability=availability, source_kind=source_kind, source_ref=source_ref,
        precision=precision, updated_at=datetime.now(timezone.utc).isoformat(),
        revision=profile.fact_revision + 1,
    )
    branch = getattr(profile, root)
    if previous and getattr(branch, name) == validated and all(
        getattr(previous, key) == getattr(metadata, key)
        for key in ("availability", "source_kind", "source_ref", "precision")
    ):
        return False
    setattr(branch, name, validated)
    profile.fact_revision += 1
    profile.fact_metadata[path] = metadata
    return True


def known_fact(profile: CaseProfile, path: str) -> tuple[bool, Any]:
    """Do not infer availability from truthiness or Pydantic defaults."""
    if path not in fact_registry():
        raise ValueError(f"Unknown fact path: {path}")
    metadata = profile.fact_metadata.get(path)
    if not metadata or metadata.availability != "known":
        return False, None
    root, name = path.split(".")
    return True, getattr(getattr(profile, root), name)
