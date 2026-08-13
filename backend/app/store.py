"""CaseProfile persistence. Uses Postgres when configured, else an in-memory dict.

The Postgres path stores the profile whole as `jsonb` in the `cases` table.
"""

from datetime import datetime, timezone
from typing import Optional

from . import db
from .models import CaseProfile, EligibilityResult, MatchLevel, SpecialistFinding

_cases = db.JsonStore("cases")
# Fallback (no-database) room_id -> case_id map. With Postgres, both API and Band worker
# processes share the mapping; in-memory only works single-process.
_room_map: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Band room <-> case mapping
#
# A Band specialist tool only knows the room it is running in (ctx.deps.room_id).
# This mapping lets the tool resolve the room back to the owning case and persist
# its structured finding. The database is the shared bus between the API and worker.
# ---------------------------------------------------------------------------
def map_room_to_case(room_id: str, case_id: str) -> None:
    if not db.available():
        _room_map[room_id] = case_id
        return
    with db.connection() as conn:
        conn.execute(
            "INSERT INTO band_rooms (room_id, case_id) VALUES (%s, %s) "
            "ON CONFLICT (room_id) DO UPDATE SET case_id = EXCLUDED.case_id",
            (room_id, case_id),
        )


def get_case_for_room(room_id: str) -> Optional[str]:
    if not db.available():
        return _room_map.get(room_id)
    with db.connection() as conn:
        row = conn.execute(
            "SELECT case_id FROM band_rooms WHERE room_id = %s", (room_id,)
        ).fetchone()
    return row[0] if row else None


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
    _cases.put(profile.id, profile.model_dump_json())


def get_profile(case_id: str) -> Optional[CaseProfile]:
    doc = _cases.get(case_id)
    return CaseProfile.model_validate(doc) if doc else None
