"""CaseProfile persistence. Uses Redis when configured, else an in-memory dict.

The Redis path stores the profile as JSON under `ilera:case:{id}`. Swap this for the
Redis Agent Memory Server when wiring long-term memory.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from .config import get_settings
from .models import CaseProfile, EligibilityResult, MatchLevel, SpecialistFinding

_memory: dict[str, str] = {}
# Fallback (no-Redis) room_id -> case_id map. With Redis, both API and Band worker
# processes share the mapping; in-memory only works single-process.
_room_map: dict[str, str] = {}


def _redis():
    settings = get_settings()
    if not settings.has_redis:
        return None
    import redis  # local import so the app boots without redis configured

    return redis.from_url(settings.redis_url, decode_responses=True)


def _key(case_id: str) -> str:
    return f"ilera:case:{case_id}"


def _room_key(room_id: str) -> str:
    return f"ilera:band:room:{room_id}"


# ---------------------------------------------------------------------------
# Band room <-> case mapping
#
# A Band specialist tool only knows the room it is running in (ctx.deps.room_id).
# This mapping lets the tool resolve the room back to the owning case and persist
# its structured finding. Redis is the shared bus between the API and worker.
# ---------------------------------------------------------------------------
def map_room_to_case(room_id: str, case_id: str) -> None:
    client = _redis()
    if client is not None:
        client.set(_room_key(room_id), case_id)
    else:
        _room_map[room_id] = case_id


def get_case_for_room(room_id: str) -> Optional[str]:
    client = _redis()
    if client is not None:
        return client.get(_room_key(room_id))
    return _room_map.get(room_id)


# ---------------------------------------------------------------------------
# match_level -> legacy (status, confidence) so the rest of the app (applications
# page, dashboard) keeps working off EligibilityResult.
# ---------------------------------------------------------------------------
_MATCH_TO_STATUS: dict[str, tuple[str, float]] = {
    "none": ("unlikely", 0.05),
    "low": ("unlikely", 0.3),
    "medium": ("possible", 0.55),
    "likely": ("likely", 0.78),
    "very_likely": ("likely", 0.93),
}


def finding_to_result(f: SpecialistFinding) -> EligibilityResult:
    status, confidence = _MATCH_TO_STATUS.get(f.match_level, ("needs_info", 0.4))
    return EligibilityResult(
        program=f.program,
        confidence=confidence,
        status=status,  # type: ignore[arg-type]
        match_level=f.match_level,
        rationale=" ".join(f.notes),
        next_steps=[],
        sources=list(f.citations),
    )


def record_finding(
    room_id: str,
    doc_key: str,
    program: str,
    match_level: MatchLevel,
    notes: list[str],
    cross_programs: list[str],
    citations: list[str],
) -> Optional[str]:
    """Persist a specialist's complete finding onto the owning case. Returns the
    case_id if resolved, else None. Also projects the finding into the legacy
    `eligibility` map so downstream pages keep working."""
    case_id = get_case_for_room(room_id)
    if not case_id:
        return None
    profile = get_profile(case_id)
    if profile is None:
        return None
    finding = SpecialistFinding(
        program=program,
        doc_key=doc_key,
        match_level=match_level,
        notes=notes,
        cross_programs=cross_programs,
        citations=citations,
        complete=True,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    profile.findings[doc_key] = finding
    profile.eligibility[program] = finding_to_result(finding)
    save_profile(profile)
    return case_id


def record_strategy(room_id: str, strategy: str) -> Optional[str]:
    """Persist the routing agent's synthesized application strategy onto the case."""
    case_id = get_case_for_room(room_id)
    if not case_id:
        return None
    profile = get_profile(case_id)
    if profile is None:
        return None
    profile.strategy = strategy
    profile.strategy_complete = True
    profile.band_status = "complete"
    profile.band_completed_at = datetime.now(timezone.utc).isoformat()
    save_profile(profile)
    return case_id


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
