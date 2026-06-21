"""Reminder scheduling — model, persistence (Redis / in-memory), and templates.

A Reminder fires a Poke message on a schedule (daily, weekly, once).
Persistence mirrors the CaseProfile pattern in store.py.
"""

import json
import uuid
from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .config import get_settings

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class ReminderKind(str, Enum):
    daily_care_log = "daily_care_log"
    appointment = "appointment"
    renewal_deadline = "renewal_deadline"
    custom = "custom"


class ScheduleFreq(str, Enum):
    daily = "daily"
    weekly = "weekly"
    once = "once"


class ReminderSchedule(BaseModel):
    freq: ScheduleFreq = ScheduleFreq.daily
    time: str = "09:00"  # HH:MM in 24-hour format
    weekday: Optional[int] = None  # 0=Mon … 6=Sun, used when freq=weekly
    date: Optional[str] = None  # ISO date, used when freq=once


class Reminder(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: Optional[str] = None
    kind: ReminderKind = ReminderKind.custom
    message: str = ""
    schedule: ReminderSchedule = Field(default_factory=ReminderSchedule)
    next_run: Optional[str] = None  # ISO datetime
    active: bool = True
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_sent_at: Optional[str] = None


# ---------------------------------------------------------------------------
# next_run computation
# ---------------------------------------------------------------------------


def compute_next_run(schedule: ReminderSchedule) -> str:
    """Return the next fire time as an ISO-8601 UTC datetime string."""
    now = datetime.now(timezone.utc)
    parts = schedule.time.split(":")
    fire_time = time(int(parts[0]), int(parts[1]), tzinfo=timezone.utc)

    if schedule.freq == ScheduleFreq.once:
        if schedule.date:
            d = date.fromisoformat(schedule.date)
        else:
            d = now.date()
        candidate = datetime.combine(d, fire_time, tzinfo=timezone.utc)
        if candidate <= now:
            return candidate.isoformat()  # already past — will fire immediately
        return candidate.isoformat()

    if schedule.freq == ScheduleFreq.daily:
        candidate = datetime.combine(now.date(), fire_time, tzinfo=timezone.utc)
        if candidate <= now:
            from datetime import timedelta

            candidate += timedelta(days=1)
        return candidate.isoformat()

    if schedule.freq == ScheduleFreq.weekly:
        weekday = schedule.weekday if schedule.weekday is not None else 0
        candidate = datetime.combine(now.date(), fire_time, tzinfo=timezone.utc)
        days_ahead = (weekday - candidate.weekday()) % 7
        if days_ahead == 0 and candidate <= now:
            days_ahead = 7
        from datetime import timedelta

        candidate += timedelta(days=days_ahead)
        return candidate.isoformat()

    return now.isoformat()


def advance_next_run(reminder: Reminder) -> None:
    """Move next_run forward after a send. Deactivates one-shot reminders."""
    if reminder.schedule.freq == ScheduleFreq.once:
        reminder.active = False
        reminder.next_run = None
    else:
        reminder.next_run = compute_next_run(reminder.schedule)


# ---------------------------------------------------------------------------
# Persistence (Redis / in-memory)
# ---------------------------------------------------------------------------

_memory: dict[str, str] = {}
_REDIS_PREFIX = "ilera:reminder:"


def _redis():
    settings = get_settings()
    if not settings.has_redis:
        return None
    import redis

    return redis.from_url(settings.redis_url, decode_responses=True)


def _key(reminder_id: str) -> str:
    return f"{_REDIS_PREFIX}{reminder_id}"


def save_reminder(reminder: Reminder) -> None:
    payload = reminder.model_dump_json()
    client = _redis()
    if client is not None:
        client.set(_key(reminder.id), payload)
    else:
        _memory[reminder.id] = payload


def get_reminder(reminder_id: str) -> Optional[Reminder]:
    client = _redis()
    raw = (
        client.get(_key(reminder_id))
        if client is not None
        else _memory.get(reminder_id)
    )
    if not raw:
        return None
    return Reminder.model_validate(json.loads(raw))


def list_reminders() -> list[Reminder]:
    client = _redis()
    if client is not None:
        keys = client.keys(f"{_REDIS_PREFIX}*")
        if not keys:
            return []
        pipe = client.pipeline()
        for k in keys:
            pipe.get(k)
        results = pipe.execute()
        return [
            Reminder.model_validate(json.loads(r)) for r in results if r
        ]
    return [
        Reminder.model_validate(json.loads(v)) for v in _memory.values()
    ]


def delete_reminder(reminder_id: str) -> bool:
    client = _redis()
    if client is not None:
        return client.delete(_key(reminder_id)) > 0
    return _memory.pop(reminder_id, None) is not None


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, dict] = {
    "daily_care_log": {
        "kind": "daily_care_log",
        "message": "",  # filled at send-time via daily_care_log_prompt()
        "schedule": {"freq": "daily", "time": "18:00"},
    },
    "ihss_timesheet": {
        "kind": "renewal_deadline",
        "message": (
            "IHSS timesheet reminder: Your timesheet is due soon. "
            "Please submit it to avoid delays in payment."
        ),
        "schedule": {"freq": "weekly", "time": "09:00", "weekday": 4},
    },
    "medi_cal_renewal": {
        "kind": "renewal_deadline",
        "message": (
            "Medi-Cal annual renewal reminder: Check your mail for the renewal packet "
            "and submit it before the deadline to keep coverage."
        ),
        "schedule": {"freq": "once", "time": "09:00"},
    },
    "pfl_weekly_cert": {
        "kind": "renewal_deadline",
        "message": (
            "Paid Family Leave weekly certification: File your weekly claim "
            "at edd.ca.gov to keep receiving PFL benefits."
        ),
        "schedule": {"freq": "weekly", "time": "09:00", "weekday": 0},
    },
    "appointment": {
        "kind": "appointment",
        "message": "Upcoming appointment reminder — check your calendar for details.",
        "schedule": {"freq": "once", "time": "09:00"},
    },
}
