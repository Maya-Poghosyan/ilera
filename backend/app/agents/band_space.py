"""Shared agent space.

This is where specialist agents coordinate to dedupe follow-up questions and resolve
cross-program benefit interactions. Today it's a lightweight in-process coordinator;
wire it to Band (https://docs.band.ai/core-concepts) to run agents as real participants
in a shared space.
"""

from ..models import EligibilityResult, FollowupQuestion


def dedupe_followups(results: list[EligibilityResult]) -> list[FollowupQuestion]:
    """Collapse near-duplicate follow-up questions across specialists."""
    seen: dict[str, FollowupQuestion] = {}
    for res in results:
        for q in res.followups:
            key = q.prompt.strip().lower()
            if key not in seen:
                seen[key] = q
    return list(seen.values())


def resolve_interactions(results: list[EligibilityResult]) -> list[str]:
    """Surface known cross-program interactions as strategy notes."""
    notes: list[str] = []
    programs = {r.program for r in results if r.status in ("likely", "possible")}
    if "IHSS" in programs and "Medi-Cal" in programs:
        notes.append("IHSS eligibility generally requires active Medi-Cal — sequence Medi-Cal first.")
    if "Paid Family Leave" in programs and "IHSS" in programs:
        notes.append("PFL wages and IHSS provider pay can interact; confirm income reporting.")
    return notes
