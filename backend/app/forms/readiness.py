"""Form-readiness: the bridge from the eligibility summary to the forms flow.

The eligibility pass already computes, per program, the documents an application needs
and the profile gaps that matter (``EligibilityResult.required_documents`` /
``missing_info`` / ``next_steps``). Intake also *deliberately defers* a set of sensitive
fields (SSN, exact bank figures, physician contact, member numbers, signatures — see
``intake.schema.DELAYED_QUESTIONS``) that government forms invariably ask for.

This module joins those two — reusing data that is already persisted on the CaseProfile
— into a per-program checklist a caregiver can act on before signing up or starting a
single PDF. It runs no LLM and does not re-trigger the Durable pipeline; it is a pure
projection of ``profile.eligibility``.
"""

from __future__ import annotations

from ..intake.schema import DELAYED_QUESTIONS
from ..models import CaseProfile, FormReadiness

# Match levels worth preparing documents for. A "none" result is not actionable, so it
# is omitted — the caregiver should not gather paperwork for a program they can't get.
_ACTIONABLE = {"low", "medium", "likely", "very_likely"}

# Strongest-first ordering, mirroring the eligibility results page.
_ORDER = {"very_likely": 0, "likely": 1, "medium": 2, "low": 3, "none": 4}


def program_readiness(profile: CaseProfile) -> list[FormReadiness]:
    """Per-program readiness for every actionable program, strongest match first.

    Reads ``profile.eligibility`` (populated by the synthesis step). Returns an empty
    list if eligibility has not completed yet — the caller can treat that as "not ready".
    """
    out: list[FormReadiness] = []
    for result in profile.eligibility.values():
        if result.match_level not in _ACTIONABLE:
            continue
        out.append(
            FormReadiness(
                program=result.program,
                match_level=result.match_level,
                required_documents=list(result.required_documents),
                missing_info=list(result.missing_info),
                next_steps=list(result.next_steps),
                # The deferred set is program-independent today: every application that
                # reaches the forms stage draws from the same withheld pool. Carrying it
                # per-program keeps the checklist self-contained for each form flow.
                withheld_fields=list(DELAYED_QUESTIONS),
            )
        )
    out.sort(key=lambda r: _ORDER.get(r.match_level, 5))
    return out
