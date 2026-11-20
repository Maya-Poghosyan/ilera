"""CaseProfile persistence.

Stores the profile whole as `jsonb` in the `cases` table.
"""

from typing import Callable, Optional, TypeVar

from app.core import db
from app.intake.mapping import apply_account_contact
from app.cases.models import CaseProfile, EligibilityResult, SpecialistFinding

_cases = db.JsonStore("cases")


# ---------------------------------------------------------------------------
# Ownership
#
# Intake is anonymous, so a case is born unowned and is claimed when its creator signs up
# or logs in. A claim is permanent: once a case has an owner, no other account can take it,
# which is what stops a stranger who guesses a case id from attaching it to themselves.
# ---------------------------------------------------------------------------
def get_case_owner(case_id: str) -> Optional[str]:
    """The owning user's id, or None for a case nobody has claimed yet."""
    with db.connection() as conn:
        row = conn.execute(
            "SELECT owner_user_id FROM cases WHERE id = %s", (case_id,)
        ).fetchone()
    return row[0] if row else None


def claim_case(case_id: str, user_id: str) -> bool:
    """Give an unclaimed case to a user. False if the case is gone or already someone else's.

    The guard is in the UPDATE rather than a read-then-write so two simultaneous claims can't
    both succeed.
    """
    with db.connection() as conn:
        cur = conn.execute(
            "UPDATE cases SET owner_user_id = %s "
            "WHERE id = %s AND (owner_user_id IS NULL OR owner_user_id = %s)",
            (user_id, case_id, user_id),
        )
    return cur.rowcount > 0


def get_case_id_for_user(user_id: str) -> Optional[str]:
    """The user's case. Most recently touched one, if they somehow own several."""
    with db.connection() as conn:
        row = conn.execute(
            "SELECT id FROM cases WHERE owner_user_id = %s ORDER BY updated_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    return row[0] if row else None


def purge_unclaimed_cases(older_than_days: int) -> int:
    """Delete cases nobody claimed within the window. An abandoned intake is otherwise kept
    forever, and it holds the household data of someone who never made an account."""
    with db.connection() as conn:
        cur = conn.execute(
            "DELETE FROM cases WHERE owner_user_id IS NULL "
            "AND updated_at < now() - make_interval(days => %s)",
            (older_than_days,),
        )
    return cur.rowcount


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


def apply_contact(case_id: str, *, name: str = "", email: str = "", phone: str = "") -> None:
    """Copy an account's contact details onto its case, where the form filler reads them."""
    profile = get_profile(case_id)
    if profile is None:
        return
    apply_account_contact(profile, name=name, email=email, phone=phone)
    save_profile(profile)


def save_profile(profile: CaseProfile) -> None:
    _cases.put(profile.id, profile.model_dump_json())


def get_profile(case_id: str) -> Optional[CaseProfile]:
    doc = _cases.get(case_id)
    return CaseProfile.model_validate(doc) if doc else None


_MutationResult = TypeVar("_MutationResult")


def mutate_profile(case_id: str, operation: Callable[[CaseProfile], tuple[CaseProfile, _MutationResult]]) -> _MutationResult:
    """Serialize resolution mutations and commit profile/tasks/results together.

    An exception rolls back the operation; the case row is locked for its duration.
    Operations must not perform I/O.
    """
    with db.connection() as conn:
        with conn.transaction():
            row = conn.execute("SELECT doc FROM cases WHERE id = %s FOR UPDATE", (case_id,)).fetchone()
            if row is None:
                raise KeyError(case_id)
            updated, result = operation(CaseProfile.model_validate(row[0]))
            conn.execute("UPDATE cases SET doc = %s::jsonb, updated_at = now() WHERE id = %s",
                         (updated.model_dump_json(), case_id))
            return result
