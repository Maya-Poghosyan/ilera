"""Per-case caregiver preferences (Postgres or in-memory fallback).

Currently just the inbox-monitoring consent flag: Poke may only look through a
caregiver's email and messages for care events while this is on. It defaults to
off so scanning is opt-in.
"""

from pydantic import BaseModel

from . import db

_store = db.JsonStore("preferences", keys=("case_id",))


class Preferences(BaseModel):
    case_id: str
    monitor_inboxes: bool = False
    monitor_inboxes_updated_at: str = ""


def get_preferences(case_id: str) -> Preferences:
    doc = _store.get(case_id)
    return Preferences.model_validate(doc) if doc else Preferences(case_id=case_id)


def save_preferences(prefs: Preferences) -> Preferences:
    _store.put(prefs.case_id, prefs.model_dump_json())
    return prefs
