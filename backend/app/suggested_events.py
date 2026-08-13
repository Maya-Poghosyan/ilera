"""Suggested events storage — persisted in Postgres or in-memory fallback.

Suggested events are calendar entries surfaced by Poke's email/message scanning
via the MCP integration. Each event includes a title, an ISO date, optional
time/kind, and a description of where it was detected.
"""

import uuid
from datetime import date as date_cls
from typing import Optional

from pydantic import BaseModel, Field, computed_field, model_validator

from . import db

_store = db.JsonStore("suggested_events")


class SuggestedEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    date: date_cls
    title: str
    time: Optional[str] = None
    kind: str = "Appointment"
    description: Optional[str] = None
    source: str = "poke"

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
        return self.date.day


def save_suggested_event(event: SuggestedEvent) -> SuggestedEvent:
    _store.put(event.id, event.model_dump_json())
    return event


def list_suggested_events() -> list[SuggestedEvent]:
    return [SuggestedEvent.model_validate(doc) for doc in _store.list()]


def get_suggested_event(event_id: str) -> Optional[SuggestedEvent]:
    doc = _store.get(event_id)
    return SuggestedEvent.model_validate(doc) if doc else None


def delete_suggested_event(event_id: str) -> bool:
    return _store.delete(event_id)
