"""Calendar events — the caregiver's committed calendar, persisted per owner.

A calendar event is a confirmed entry on the care calendar. Unlike a `SuggestedEvent`
(a provider-independent *suggestion* awaiting review), a calendar event has been accepted
by the caregiver and shows up as real data on the month grid.

Acceptance from a suggestion is idempotent: accepting the same suggestion twice yields the
same single calendar event. This is enforced by deriving the calendar event id from the
source suggestion id, so a duplicate accept overwrites rather than inserts a second row.
"""

import uuid
from datetime import date as date_cls
from typing import Optional

from pydantic import BaseModel, Field, computed_field

from . import db

_store = db.JsonStore("calendar_events")


class CalendarEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    date: Optional[date_cls] = None
    timezone: Optional[str] = None
    title: str
    time: Optional[str] = None
    kind: str = "Appointment"
    description: Optional[str] = None
    # Where this event came from: "manual" or "email" (via an accepted suggestion).
    source: str = "manual"
    # The suggestion this was accepted from, if any. Makes acceptance idempotent.
    source_suggestion_id: Optional[str] = None
    user_id: Optional[str] = None
    case_id: Optional[str] = None

    @computed_field
    @property
    def day(self) -> int:
        return self.date.day if self.date else 0


def _event_id_for_suggestion(suggestion_id: str) -> str:
    """Deterministic id so re-accepting a suggestion never creates a duplicate."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"ilera:calendar:{suggestion_id}").hex[:12]


def save_calendar_event(event: CalendarEvent) -> CalendarEvent:
    _store.put(event.id, event.model_dump_json())
    return event


def accept_from_suggestion(
    *,
    suggestion_id: str,
    user_id: str,
    case_id: Optional[str],
    date: Optional[date_cls],
    timezone: Optional[str],
    title: str,
    time: Optional[str],
    kind: str,
    description: Optional[str],
) -> CalendarEvent:
    """Create (or refresh) the calendar event for a suggestion. Idempotent by suggestion id."""
    event = CalendarEvent(
        id=_event_id_for_suggestion(suggestion_id),
        date=date,
        timezone=timezone,
        title=title,
        time=time,
        kind=kind,
        description=description,
        source="email",
        source_suggestion_id=suggestion_id,
        user_id=user_id,
        case_id=case_id,
    )
    return save_calendar_event(event)


def list_calendar_events(*, user_id: Optional[str] = None) -> list[CalendarEvent]:
    if user_id is not None and db.available():
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT doc FROM calendar_events WHERE doc->>'user_id' = %s",
                (user_id,),
            ).fetchall()
        return [CalendarEvent.model_validate(row[0]) for row in rows]
    return [
        CalendarEvent.model_validate(doc)
        for doc in _store.list()
        if user_id is None or doc.get("user_id") == user_id
    ]


def get_calendar_event(event_id: str) -> Optional[CalendarEvent]:
    doc = _store.get(event_id)
    return CalendarEvent.model_validate(doc) if doc else None


def delete_calendar_event(event_id: str) -> bool:
    return _store.delete(event_id)
