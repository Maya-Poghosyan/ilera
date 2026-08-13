"""Records & Renewal — timekeeping, care journal, and renewal tracking.

Persistence mirrors the CaseProfile pattern in store.py / reminders.py:
Postgres when configured, else an in-memory dict.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from . import db

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

_FALL_PATTERN = re.compile(
    r"\b(fall|fell|tripped|slipped|stumbled|lost\s+balance)\b",
    re.IGNORECASE,
)


def _detect_fall(text: str) -> bool:
    """Simple keyword heuristic to flag fall-related journal entries."""
    return bool(_FALL_PATTERN.search(text))


class TimekeepingEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    date: str  # ISO date (YYYY-MM-DD)
    hours: float
    start_time: Optional[str] = None  # HH:MM
    end_time: Optional[str] = None  # HH:MM
    service_type: str = "personal_care"  # personal_care | domestic | paramedical | accompaniment
    tasks: list[str] = Field(default_factory=list)
    notes: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class JournalEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    date: str  # ISO date (YYYY-MM-DD)
    text: str
    fall_flagged: bool = False
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class RenewalInfo(BaseModel):
    case_id: str
    program: str = "IHSS"
    due_date: Optional[str] = None  # ISO date
    status: str = "active"  # active | pending | overdue


# ---------------------------------------------------------------------------
# Persistence (Postgres / in-memory)
# ---------------------------------------------------------------------------

_timekeeping = db.JsonStore("timekeeping", scoped_by_case=True)
_journal = db.JsonStore("journal", scoped_by_case=True)
_renewals = db.JsonStore("renewals", keys=("case_id",))


# --- Timekeeping ---


def save_timekeeping(entry: TimekeepingEntry) -> None:
    _timekeeping.put(entry.id, entry.model_dump_json(), case_id=entry.case_id)


def get_timekeeping(entry_id: str, case_id: str) -> Optional[TimekeepingEntry]:
    doc = _timekeeping.get(entry_id)
    if not doc or doc.get("case_id") != case_id:
        return None
    return TimekeepingEntry.model_validate(doc)


def list_timekeeping(case_id: str) -> list[TimekeepingEntry]:
    return [TimekeepingEntry.model_validate(doc) for doc in _timekeeping.list(case_id)]


def delete_timekeeping(entry_id: str, case_id: str) -> bool:
    if get_timekeeping(entry_id, case_id) is None:
        return False
    return _timekeeping.delete(entry_id)


# --- Journal ---


def save_journal(entry: JournalEntry) -> None:
    _journal.put(entry.id, entry.model_dump_json(), case_id=entry.case_id)


def get_journal(entry_id: str, case_id: str) -> Optional[JournalEntry]:
    doc = _journal.get(entry_id)
    if not doc or doc.get("case_id") != case_id:
        return None
    return JournalEntry.model_validate(doc)


def list_journal(case_id: str) -> list[JournalEntry]:
    return [JournalEntry.model_validate(doc) for doc in _journal.list(case_id)]


def delete_journal(entry_id: str, case_id: str) -> bool:
    if get_journal(entry_id, case_id) is None:
        return False
    return _journal.delete(entry_id)


# --- Renewal ---


def save_renewal(info: RenewalInfo) -> None:
    _renewals.put(info.case_id, info.model_dump_json())


def get_renewal(case_id: str) -> Optional[RenewalInfo]:
    doc = _renewals.get(case_id)
    return RenewalInfo.model_validate(doc) if doc else None
