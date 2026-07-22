"""Suggested events storage — persisted in Redis or in-memory fallback.

Suggested events are calendar entries surfaced by Poke's email/message scanning
via the MCP integration. Each event includes a title, day, optional time/kind,
and a description of where it was detected.
"""

import json
import uuid
from typing import Optional

from pydantic import BaseModel, Field

from .config import get_settings

_PREFIX = "ilera:suggested_event:"

_memory: dict[str, str] = {}


class SuggestedEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    day: int
    title: str
    time: Optional[str] = None
    kind: str = "Appointment"
    description: Optional[str] = None
    source: str = "poke"


def _redis():
    settings = get_settings()
    if not settings.has_redis:
        return None
    import redis

    return redis.from_url(settings.redis_url, decode_responses=True)


def save_suggested_event(event: SuggestedEvent) -> SuggestedEvent:
    payload = event.model_dump_json()
    client = _redis()
    if client is not None:
        client.set(f"{_PREFIX}{event.id}", payload)
    else:
        _memory[event.id] = payload
    return event


def list_suggested_events() -> list[SuggestedEvent]:
    client = _redis()
    if client is not None:
        keys = client.keys(f"{_PREFIX}*")
        items = [client.get(k) for k in keys]
    else:
        items = list(_memory.values())
    return [SuggestedEvent.model_validate(json.loads(raw)) for raw in items if raw]


def get_suggested_event(event_id: str) -> Optional[SuggestedEvent]:
    client = _redis()
    raw = (
        client.get(f"{_PREFIX}{event_id}")
        if client is not None
        else _memory.get(event_id)
    )
    if not raw:
        return None
    return SuggestedEvent.model_validate(json.loads(raw))


def delete_suggested_event(event_id: str) -> bool:
    client = _redis()
    if client is not None:
        return bool(client.delete(f"{_PREFIX}{event_id}"))
    return _memory.pop(event_id, None) is not None
