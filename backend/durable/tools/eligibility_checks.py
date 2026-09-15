"""Pure-Python eligibility gate functions.

Each gate runs a fast, deterministic check against the CaseProfile and returns a
three-tuple (skip, reason, fast_match_level).  A skip=True result means the program
is clearly ineligible and the LLM specialist activity should be bypassed entirely —
saving latency and cost.

Design notes:
- Gates are deliberately conservative: when in doubt they return skip=False and let
  the specialist LLM make the call.  A false positive skip (wrong disqualification)
  is worse than running an unnecessary LLM call.
- None / missing fields never trigger a skip — only hard, certain disqualifications do.
- fast_match_level is the MatchLevel written into the final finding when skip=True.
  It is almost always "none", but gates may return "low" if the program is unlikely
  but not completely ruled out.
"""

from __future__ import annotations

from typing import Callable

from app.models import CaseProfile

# Return type: (skip, reason, fast_match_level)
GateResult = tuple[bool, str, str]


def check_ihss(profile: CaseProfile) -> GateResult:
    """IHSS is California-only.

    Skip immediately if the care recipient's state is explicitly set to something
    other than CA / California.  Unknown / empty state → let specialist decide.
    """
    state = (profile.care_recipient.state or "").strip()
    if state and state.upper() not in {"CA", "CALIFORNIA"}:
        return (
            True,
            f"IHSS is a California-only program (care recipient state: {state})",
            "none",
        )
    return False, "", "none"


def check_va(profile: CaseProfile) -> GateResult:
    """VA Caregiver Support programs require the care recipient to be a veteran.

    The `veteran` flag defaults to False, so only skip when it is explicitly False
    (not just unset).  The CareRecipient model has `veteran: bool = False`, so this
    is reliable.
    """
    if not profile.care_recipient.veteran:
        return (
            True,
            "VA Caregiver Support programs require the care recipient to be a veteran",
            "none",
        )
    return False, "", "none"


def check_medicare(profile: CaseProfile) -> GateResult:
    """Skip Medicare if the care recipient is clearly too young and not enrolled.

    The 55-year threshold is well below the standard age-65 eligibility threshold,
    giving room for the specialist to assess SSDI early-enrollment pathways.
    If age is unknown we do not skip — the specialist will ask.
    """
    cr = profile.care_recipient
    age = cr.age  # may be None
    insurance = (cr.insurance or "").lower()

    # Already on Medicare — definitely worth assessing.
    if insurance == "medicare":
        return False, "", "none"

    # Age known and clearly below the conservative threshold.
    if age is not None and age < 55:
        return (
            True,
            f"Care recipient age {age} is below the minimum Medicare threshold (55)",
            "none",
        )

    return False, "", "none"


def check_pfl(profile: CaseProfile) -> GateResult:
    """Skip CA Paid Family Leave only when employment status clearly disqualifies.

    PFL requires SDI-covered wages.  Self-employed, unemployed, and retired statuses
    are ineligible — but only skip when caregiver is in CA (PFL is CA-only) AND one of
    those ineligible statuses is confirmed.  Unknown or empty status → let specialist decide.
    """
    cg = profile.caregiver
    status = (cg.employment_status or "").strip().lower()
    state = (cg.state or "").strip().upper()

    if not status:
        # No employment info: conservative, let specialist handle.
        return False, "", "none"

    ineligible_statuses = {"self-employed", "self employed", "unemployed", "retired"}
    clearly_ineligible = status in ineligible_statuses or status.startswith("self-employ")

    if clearly_ineligible and state and state not in {"CA", "CALIFORNIA"}:
        return (
            True,
            f"CA Paid Family Leave requires SDI-covered wages; caregiver employment "
            f"status '{cg.employment_status}' in state '{cg.state}' is not covered",
            "none",
        )

    return False, "", "none"


def check_medical(profile: CaseProfile) -> GateResult:
    """Skip Medi-Cal only when household income far exceeds any realistic threshold.

    Uses a very conservative $12,000/month × household-size ceiling to avoid false
    positives — the actual income limits are much lower, but the specialist will
    apply the real FPL-based thresholds.  Missing income data → do not skip.
    """
    hh = profile.household
    income = hh.income_monthly
    size = hh.size or 1

    if income is None:
        return False, "", "none"

    ceiling = 12_000.0 * size
    if income > ceiling:
        return (
            True,
            f"Household income ${income:,.0f}/month significantly exceeds Medi-Cal limits "
            f"for a household of {size}",
            "none",
        )

    return False, "", "none"


def check_tax(profile: CaseProfile) -> GateResult:  # noqa: ARG001
    """Caregiver Tax Relief is always worth assessing — never skip.

    Nearly all caregivers can benefit from at least one of: Credit for Other
    Dependents, Child & Dependent Care Credit, medical-expense deductions, or the
    IRS Notice 2014-7 IHSS/Medicaid-waiver income exclusion.
    """
    return False, "", "none"


# Registry: doc_key → gate function.  Must cover every key in ALL_SPECIALISTS.
GATES: dict[str, Callable[[CaseProfile], GateResult]] = {
    "ihss": check_ihss,
    "medical": check_medical,
    "pfl": check_pfl,
    "va": check_va,
    "medicare": check_medicare,
    "tax": check_tax,
}
