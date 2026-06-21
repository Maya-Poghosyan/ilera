"""CaseProfile persistence. Uses Redis when configured, else an in-memory dict.

The Redis path stores the profile as JSON under `ilera:case:{id}`. Swap this for the
Redis Agent Memory Server when wiring long-term memory.
"""

import json
from typing import Optional

from .config import get_settings
from .models import CaseProfile

_memory: dict[str, str] = {}


def _redis():
    settings = get_settings()
    if not settings.has_redis:
        return None
    import redis  # local import so the app boots without redis configured

    return redis.from_url(settings.redis_url, decode_responses=True)


def _key(case_id: str) -> str:
    return f"ilera:case:{case_id}"


def save_profile(profile: CaseProfile) -> None:
    payload = profile.model_dump_json()
    client = _redis()
    if client is not None:
        client.set(_key(profile.id), payload)
    else:
        _memory[profile.id] = payload


def get_profile(case_id: str) -> Optional[CaseProfile]:
    client = _redis()
    raw = client.get(_key(case_id)) if client is not None else _memory.get(case_id)
    if not raw:
        return None
    return CaseProfile.model_validate(json.loads(raw))
