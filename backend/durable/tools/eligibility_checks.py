"""Pure-Python eligibility gate functions.

Each gate runs a fast, deterministic check against the CaseProfile and returns a
three-tuple (skip, reason, fast_match_level).  A skip=True result means the LLM
specialist activity should be bypassed entirely — saving latency and cost — because
the gate has already made a confident determination.

A skip can happen for two opposite reasons:
- CLEAR INELIGIBILITY — a hard, certain disqualification (fast_match_level="none").
- ALREADY ENROLLED — the care recipient explicitly told us they currently receive
  this program.  Current enrollment is itself proof of eligibility, so the gate
  short-circuits with fast_match_level="very_likely" and a positive reason.  This
  runs BEFORE any disqualification check: someone already on Medi-Cal is eligible for
  Medi-Cal regardless of what a reported income range might otherwise suggest.

Design notes:
- Gates are deliberately conservative on the ineligibility side: when in doubt they
  return skip=False and let the specialist LLM make the call.  A false positive skip
  (wrong disqualification) is worse than running an unnecessary LLM call.
- None / missing fields never trigger an ineligibility skip — only hard, certain
  disqualifications do.
- fast_match_level is the MatchLevel written into the final finding when skip=True:
  "none" for a disqualification, "very_likely" for a confirmed current enrollment.
"""

from __future__ import annotations

from typing import Callable

from app.models import CaseProfile

# pydantic-ai is only installed where the specialist agent actually runs (the Durable
# Function App). It is imported for real when available so that `make_gate_tool`'s tool
# function has a resolvable `RunContext` annotation at agent-build time — pydantic-ai
# evaluates tool type hints via typing.get_type_hints(), which looks names up in this
# module's globals. When pydantic-ai is absent (e.g. unit-testing the pure gate
# functions), `RunContext` falls back to Any; the tool factory is simply never called
# in that environment, so the fallback is never exercised at runtime.
try:  # pragma: no cover - import shape depends on environment
    from pydantic_ai import RunContext
except ModuleNotFoundError:  # pragma: no cover
    from typing import Any as RunContext  # type: ignore[assignment]

# Return type: (skip, reason, fast_match_level)
GateResult = tuple[bool, str, str]

# MatchLevel used when a gate confirms the recipient already receives the program.
# Current enrollment is proof of eligibility, so this is the strongest positive level.
_ENROLLED_MATCH_LEVEL = "very_likely"


def _norm(values) -> set[str]:
    """Lower-cased, stripped set of strings from a list-ish profile field."""
    return {str(v).strip().lower() for v in (values or []) if str(v).strip()}


def check_enrolled(profile: CaseProfile, doc_key: str) -> GateResult:
    """Return a positive gate result when the recipient already receives `doc_key`.

    A program the care recipient explicitly reports currently receiving is, by
    definition, one they are eligible for — so we skip the LLM specialist and record a
    "very_likely" finding with a plain-language reason.  Returns skip=False when there
    is no clear enrollment signal, letting the normal disqualification checks and/or the
    specialist LLM decide.

    Signals are read from the structured profile fields that intake.mapping projects
    from the screening answers:
      - care_recipient.insurance        ("medi-cal" / "medicare")
      - care_recipient.current_benefits (free-text benefit labels)
      - care_recipient.veteran          (VA)
    plus the raw screening answers (health_coverage, medicaid_status) which carry the
    most explicit "enrolled now" signal.
    """
    cr = profile.care_recipient
    answers = profile.answers or {}
    insurance = (cr.insurance or "").strip().lower()
    benefits = _norm(cr.current_benefits)
    coverage = _norm(answers.get("recipient.health_coverage"))
    medicaid_status = str(answers.get("recipient.medicaid_status") or "").strip().lower()

    enrolled = False
    if doc_key == "medical":
        # Medi-Cal / Medicaid.
        enrolled = (
            insurance == "medi-cal"
            or medicaid_status == "enrolled now"
            or bool(coverage & {"medicaid", "both medicare and medicaid"})
            or "medicaid home- and community-based services" in benefits
        )
    elif doc_key == "medicare":
        enrolled = (
            insurance == "medicare"
            or bool(coverage & {"medicare", "both medicare and medicaid"})
        )
    elif doc_key == "va":
        # VA Caregiver Support: only treat as enrolled when a VA benefit/coverage is
        # explicitly present — the bare `veteran` flag means potentially eligible, not
        # enrolled, so that case is left to the specialist.
        enrolled = (
            "va health care" in coverage
            or bool(benefits & {
                "va disability compensation",
                "va pension or aid and attendance",
            })
        )

    if enrolled:
        return (
            True,
            f"{profile_program_label(doc_key)} is already active for the care recipient, "
            "so they are eligible.",
            _ENROLLED_MATCH_LEVEL,
        )
    return False, "", "none"


# doc_key → friendly program label for enrollment reasons (kept local to avoid importing
# the specialist registry, which this module is a dependency of).
_PROGRAM_LABELS = {
    "medical": "Medi-Cal",
    "medicare": "Medicare",
    "va": "VA Caregiver Support",
    "ihss": "IHSS",
    "pfl": "Paid Family Leave",
    "tax": "Caregiver Tax Relief",
}


def profile_program_label(doc_key: str) -> str:
    return _PROGRAM_LABELS.get(doc_key, doc_key)


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

    An explicit VA benefit/coverage signal short-circuits to "very_likely" first.
    """
    enrolled = check_enrolled(profile, "va")
    if enrolled[0]:
        return enrolled

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

    # Already on Medicare — enrollment proves eligibility; short-circuit positive.
    enrolled = check_enrolled(profile, "medicare")
    if enrolled[0]:
        return enrolled
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

    PFL pays wage replacement out of CA State Disability Insurance (SDI), so it
    requires SDI-covered wages.  Unemployed and retired caregivers have no wages and
    are ineligible.  Self-employed caregivers are NOT hard-skipped — they can opt into
    SDI via Disability Insurance Elective Coverage (DIEC) — so the specialist decides.

    Two independent deterministic disqualifiers:
      1. The caregiver works in a state other than California (CA PFL covers CA
         wages only).
      2. The caregiver is unemployed or retired (no SDI-covered wages, any state).

    Unknown / empty employment status → do not skip; let the specialist ask.
    """
    cg = profile.caregiver
    status = (cg.employment_status or "").strip().lower()
    state = (cg.state or "").strip().upper()

    # Case 2: out-of-state caregiver — CA PFL covers CA wages only.
    if state and state not in {"CA", "CALIFORNIA"}:
        return (
            True,
            f"CA Paid Family Leave covers California wages; caregiver works in "
            f"'{cg.state}', not California",
            "none",
        )

    if not status:
        # No employment info: conservative, let specialist handle.
        return False, "", "none"

    # Case 1: unemployed / retired caregivers have no wages at all, so no SDI
    # coverage, in any state.  Self-employed is deliberately NOT a hard skip:
    # self-employed people can opt into CA SDI via Disability Insurance Elective
    # Coverage (DIEC), so that case is left to the specialist to assess.
    ineligible_statuses = {"unemployed", "retired", "not employed", "not working"}

    if status in ineligible_statuses:
        return (
            True,
            f"CA Paid Family Leave requires SDI-covered wages; caregiver employment "
            f"status '{cg.employment_status}' means no SDI-covered wages",
            "none",
        )

    return False, "", "none"


def check_medical(profile: CaseProfile) -> GateResult:
    """Skip Medi-Cal only when household income far exceeds any realistic threshold.

    Uses a very conservative $12,000/month × household-size ceiling to avoid false
    positives — the actual income limits are much lower, but the specialist will
    apply the real FPL-based thresholds.  Missing income data → do not skip.

    An already-enrolled recipient short-circuits to "very_likely" and is checked
    first — current Medi-Cal enrollment proves eligibility regardless of a reported
    income range.
    """
    enrolled = check_enrolled(profile, "medical")
    if enrolled[0]:
        return enrolled

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


def make_gate_tool(doc_key: str) -> Callable[..., str]:
    """Return a pydantic-ai-compatible async tool function that runs the eligibility gate.

    The tool reads the CaseProfile from the agent's deps (RunContext) so no arguments
    are needed — the model calls it with no parameters.

    The agent must call this tool first before doing any RAG retrieval or assessment.
    If the gate returns INELIGIBLE, the agent must immediately return match_level='none'
    with the reason as the sole note — no further tool calls needed.
    """
    gate_fn = GATES.get(doc_key)

    async def check_program_gate(ctx: "RunContext[CaseProfile]") -> str:
        """Run the deterministic eligibility gate for this program.

        Call this FIRST before any other tool. Returns one of:
        - "ELIGIBLE: proceed with full assessment" — continue with lookup_program_docs
        - "ALREADY ENROLLED: <reason>" — the recipient already receives this program;
          return match_level='very_likely' immediately, no further calls needed.
        - "INELIGIBLE: <reason>" — return match_level='none' immediately, no further calls needed.
        """
        if gate_fn is None:
            return "ELIGIBLE: no gate configured for this program, proceed with full assessment"
        try:
            skip, reason, fast_match_level = gate_fn(ctx.deps)
        except Exception:
            # Conservative: gate errors should not block the assessment.
            return "ELIGIBLE: gate check inconclusive, proceed with full assessment"
        if skip:
            if fast_match_level == _ENROLLED_MATCH_LEVEL:
                return f"ALREADY ENROLLED: {reason}"
            return f"INELIGIBLE: {reason}"
        return "ELIGIBLE: proceed with full assessment"

    return check_program_gate
