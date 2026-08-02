"""Per-case caregiver preferences (Redis or in-memory fallback).

Currently just the inbox-monitoring consent flag: Poke may only look through a
caregiver's email and messages for care events while this is on. It defaults to
off so scanning is opt-in.
"""

import json

from pydantic import BaseModel

from .config import get_settings

_PREFIX = "ilera:preferences:"

_memory: dict[str, str] = {}


class Preferences(BaseModel):
    case_id: str
    monitor_inboxes: bool = False
    monitor_inboxes_updated_at: str = ""


def _redis():
    settings = get_settings()
    if not settings.has_redis:
        return None
    import redis

    return redis.from_url(settings.redis_url, decode_responses=True)


def get_preferences(case_id: str) -> Preferences:
    client = _redis()
    raw = client.get(f"{_PREFIX}{case_id}") if client is not None else _memory.get(case_id)
    if not raw:
        return Preferences(case_id=case_id)
    return Preferences.model_validate(json.loads(raw))


def save_preferences(prefs: Preferences) -> Preferences:
    payload = prefs.model_dump_json()
    client = _redis()
    if client is not None:
        client.set(f"{_PREFIX}{prefs.case_id}", payload)
    else:
        _memory[prefs.case_id] = payload
    return prefs
