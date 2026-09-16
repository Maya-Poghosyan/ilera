"""Records & Renewal — timekeeping, care journal, and renewal tracking.

Persistence mirrors the CaseProfile pattern in store.py / reminders.py:
Postgres when configured, else an in-memory dict.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, computed_field

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
    incident_status: str = "unreviewed"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# A renewal's derived urgency, computed from its due date. `status` below is the
# caregiver-set lifecycle; `urgency` is what the UI badges and any scheduler read.
RenewalUrgency = str  # "overdue" | "due_soon" | "upcoming" | "no_date"

# A due date within this many days (inclusive) is "due_soon".
DUE_SOON_DAYS = 30


def compute_urgency(due_date: Optional[str], today: Optional[str] = None) -> str:
    """Derive urgency from a due date, independent of the caregiver-set status.

    Returns one of: overdue, due_soon, upcoming, no_date. `today` (ISO date) is
    injectable for deterministic tests; it defaults to the current UTC date.
    """
    if not due_date:
        return "no_date"
    from datetime import date as _date

    ref = _date.fromisoformat(today) if today else datetime.now(timezone.utc).date()
    due = _date.fromisoformat(due_date)
    delta = (due - ref).days
    if delta < 0:
        return "overdue"
    if delta <= DUE_SOON_DAYS:
        return "due_soon"
    return "upcoming"


class RenewalItem(BaseModel):
    """A single program's renewal. A case can have many (IHSS, Medi-Cal, PFL, VA…)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    program: str = "IHSS"
    due_date: Optional[str] = None  # ISO date
    status: str = "active"  # active | pending | overdue — caregiver-set lifecycle
    notes: str = ""
    last_completed_date: Optional[str] = None  # ISO date the renewal was last filed
    renewal_period_months: Optional[int] = None  # cadence, e.g. 12 for annual
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def urgency(self) -> str:
        return compute_urgency(self.due_date)


# ---------------------------------------------------------------------------
# Persistence (Postgres / in-memory)
# ---------------------------------------------------------------------------

_timekeeping = db.JsonStore("timekeeping", scoped_by_case=True)
_journal = db.JsonStore("journal", scoped_by_case=True)
# Multi-renewal store: many rows per case, one per program renewal.
_renewal_items = db.JsonStore("renewal_items", keys=("case_id", "id"))


# --- Timekeeping ---


def save_timekeeping(entry: TimekeepingEntry) -> None:
    _timekeeping.put(entry.id, entry.model_dump_json(), case_id=entry.case_id)


def get_timekeeping(entry_id: str, case_id: str) -> Optional[TimekeepingEntry]:
    doc = _timekeeping.get(entry_id)
    if not doc or doc.get("case_id") != case_id:
        return None
    return TimekeepingEntry.model_validate(doc)


def list_timekeeping(case_id: str) -> list[TimekeepingEntry]:
    return sorted([TimekeepingEntry.model_validate(doc) for doc in _timekeeping.list(case_id)], key=lambda e: (e.date, e.created_at, e.id), reverse=True)


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
    return sorted([JournalEntry.model_validate(doc) for doc in _journal.list(case_id)], key=lambda e: (e.date, e.created_at, e.id), reverse=True)


def delete_journal(entry_id: str, case_id: str) -> bool:
    if get_journal(entry_id, case_id) is None:
        return False
    return _journal.delete(entry_id)


# --- Renewals (multiple per case) ---


def save_renewal_item(item: RenewalItem) -> None:
    _renewal_items.put((item.case_id, item.id), item.model_dump_json())


def get_renewal_item(case_id: str, item_id: str) -> Optional[RenewalItem]:
    doc = _renewal_items.get((case_id, item_id))
    return RenewalItem.model_validate(doc) if doc else None


def list_renewal_items(case_id: str) -> list[RenewalItem]:
    items = [RenewalItem.model_validate(doc) for doc in _renewal_items.list(case_id)]
    # Undated renewals sort last; otherwise soonest due date first.
    return sorted(
        items,
        key=lambda r: (r.due_date is None, r.due_date or "", r.program, r.id),
    )


def delete_renewal_item(case_id: str, item_id: str) -> bool:
    if get_renewal_item(case_id, item_id) is None:
        return False
    return _renewal_items.delete((case_id, item_id))
