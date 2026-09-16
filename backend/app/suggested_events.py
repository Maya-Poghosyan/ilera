"""Suggested events storage — persisted in Postgres or in-memory fallback.

Suggested events are provider-independent calendar suggestions. Each event includes a title, an ISO date, optional
time/kind, and a description of where it was detected.
"""

import uuid
from datetime import date as date_cls
from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field, model_validator

from . import db

_store = db.JsonStore("suggested_events")


class SuggestedEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    date: Optional[date_cls] = None
    date_status: Literal["known", "ambiguous", "missing"] = "known"
    timezone: Optional[str] = None
    title: str
    time: Optional[str] = None
    kind: str = "Appointment"
    description: Optional[str] = None
    source: str = "manual"
    user_id: Optional[str] = None
    case_id: Optional[str] = None
    connection_id: Optional[str] = None
    provider_message_id: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    action_required: Optional[str] = None
    model_version: Optional[str] = None
    status: Literal["pending", "accepted", "dismissed"] = "pending"

    @model_validator(mode="before")
    @classmethod
    def _upgrade_day_only(cls, data: object) -> object:
        """Read records written before events carried a full date."""
        if isinstance(data, dict) and not data.get("date") and data.get("day"):
            today = date_cls.today()
            data = {**data, "date": today.replace(day=int(data["day"])).isoformat()}
        return data

    @computed_field
    @property
    def day(self) -> int:
        return self.date.day if self.date else 0


def save_suggested_event(event: SuggestedEvent) -> SuggestedEvent:
    _store.put(event.id, event.model_dump_json())
    return event


def list_suggested_events(*, user_id: Optional[str] = None) -> list[SuggestedEvent]:
    if user_id is not None and db.available():
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT doc FROM suggested_events WHERE doc->>'user_id' = %s",
                (user_id,),
            ).fetchall()
        return [SuggestedEvent.model_validate(row[0]) for row in rows]
    return [
        SuggestedEvent.model_validate(doc) for doc in _store.list()
        if user_id is None or doc.get("user_id") == user_id
    ]


def get_suggested_event(event_id: str) -> Optional[SuggestedEvent]:
    doc = _store.get(event_id)
    return SuggestedEvent.model_validate(doc) if doc else None


def delete_suggested_event(event_id: str) -> bool:
    return _store.delete(event_id)
