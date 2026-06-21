"""Records & Renewal — timekeeping, care journal, and renewal tracking.

Persistence mirrors the CaseProfile pattern in store.py / reminders.py:
Redis when configured, else an in-memory dict. All keys use the `ilera:` namespace.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .config import get_settings

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
# Persistence (Redis / in-memory)
# ---------------------------------------------------------------------------

_timekeeping_mem: dict[str, str] = {}
_journal_mem: dict[str, str] = {}
_renewal_mem: dict[str, str] = {}

_TIMEKEEPING_PREFIX = "ilera:timekeeping:"
_JOURNAL_PREFIX = "ilera:journal:"
_RENEWAL_PREFIX = "ilera:renewal:"


def _redis():
    settings = get_settings()
    if not settings.has_redis:
        return None
    import redis

    return redis.from_url(settings.redis_url, decode_responses=True)


# --- Timekeeping ---


def save_timekeeping(entry: TimekeepingEntry) -> None:
    payload = entry.model_dump_json()
    client = _redis()
    key = f"{_TIMEKEEPING_PREFIX}{entry.case_id}:{entry.id}"
    if client is not None:
        client.set(key, payload)
    else:
        _timekeeping_mem[entry.id] = payload


def get_timekeeping(entry_id: str, case_id: str) -> Optional[TimekeepingEntry]:
    client = _redis()
    key = f"{_TIMEKEEPING_PREFIX}{case_id}:{entry_id}"
    if client is not None:
        raw = client.get(key)
    else:
        raw = _timekeeping_mem.get(entry_id)
    if not raw:
        return None
    return TimekeepingEntry.model_validate(json.loads(raw))


def list_timekeeping(case_id: str) -> list[TimekeepingEntry]:
    client = _redis()
    if client is not None:
        keys = client.keys(f"{_TIMEKEEPING_PREFIX}{case_id}:*")
        if not keys:
            return []
        pipe = client.pipeline()
        for k in keys:
            pipe.get(k)
        results = pipe.execute()
        return [
            TimekeepingEntry.model_validate(json.loads(r))
            for r in results
            if r
        ]
    return [
        TimekeepingEntry.model_validate(json.loads(v))
        for v in _timekeeping_mem.values()
        if json.loads(v).get("case_id") == case_id
    ]


def delete_timekeeping(entry_id: str, case_id: str) -> bool:
    client = _redis()
    key = f"{_TIMEKEEPING_PREFIX}{case_id}:{entry_id}"
    if client is not None:
        return client.delete(key) > 0
    return _timekeeping_mem.pop(entry_id, None) is not None


# --- Journal ---


def save_journal(entry: JournalEntry) -> None:
    payload = entry.model_dump_json()
    client = _redis()
    key = f"{_JOURNAL_PREFIX}{entry.case_id}:{entry.id}"
    if client is not None:
        client.set(key, payload)
    else:
        _journal_mem[entry.id] = payload


def get_journal(entry_id: str, case_id: str) -> Optional[JournalEntry]:
    client = _redis()
    key = f"{_JOURNAL_PREFIX}{case_id}:{entry_id}"
    if client is not None:
        raw = client.get(key)
    else:
        raw = _journal_mem.get(entry_id)
    if not raw:
        return None
    return JournalEntry.model_validate(json.loads(raw))


def list_journal(case_id: str) -> list[JournalEntry]:
    client = _redis()
    if client is not None:
        keys = client.keys(f"{_JOURNAL_PREFIX}{case_id}:*")
        if not keys:
            return []
        pipe = client.pipeline()
        for k in keys:
            pipe.get(k)
        results = pipe.execute()
        return [
            JournalEntry.model_validate(json.loads(r))
            for r in results
            if r
        ]
    return [
        JournalEntry.model_validate(json.loads(v))
        for v in _journal_mem.values()
        if json.loads(v).get("case_id") == case_id
    ]


def delete_journal(entry_id: str, case_id: str) -> bool:
    client = _redis()
    key = f"{_JOURNAL_PREFIX}{case_id}:{entry_id}"
    if client is not None:
        return client.delete(key) > 0
    return _journal_mem.pop(entry_id, None) is not None


# --- Renewal ---


def save_renewal(info: RenewalInfo) -> None:
    payload = info.model_dump_json()
    client = _redis()
    key = f"{_RENEWAL_PREFIX}{info.case_id}"
    if client is not None:
        client.set(key, payload)
    else:
        _renewal_mem[info.case_id] = payload


def get_renewal(case_id: str) -> Optional[RenewalInfo]:
    client = _redis()
    key = f"{_RENEWAL_PREFIX}{case_id}"
    if client is not None:
        raw = client.get(key)
    else:
        raw = _renewal_mem.get(case_id)
    if not raw:
        return None
    return RenewalInfo.model_validate(json.loads(raw))
