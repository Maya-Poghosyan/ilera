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
from app.eligibility.facts import known_fact

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


def _evidence(profile: CaseProfile, path: str, answer_id: str):
    """Canonical evidence wins; use explicit older answers only without metadata."""
    if path in profile.fact_metadata:
        available, value = known_fact(profile, path)
        return value if available else None
    return profile.answers.get(answer_id)


def check_enrolled(profile: CaseProfile, doc_key: str) -> GateResult:
    """Current coverage signals are specific to the program and evidence source."""
    coverage = _norm(_evidence(profile, "care_recipient.health_coverage", "recipient.health_coverage"))
    status = _evidence(profile, "care_recipient.medicaid_status", "recipient.medicaid_status")
    if doc_key == "medical":
        # Contradictory enrollment answers require review rather than a shortcut.
        if status not in (None, "", "Enrolled now", "I'm not sure"):
            return False, "", "none"
        enrolled = status == "Enrolled now" or bool(coverage & {"medicaid", "both medicare and medicaid"})
    elif doc_key == "medicare":
        if "Neither" in (profile.answers.get("recipient.medicare_parts") or []):
            return False, "", "none"
        enrolled = bool(coverage & {"medicare", "both medicare and medicaid"})
    else:
        # VA health care/pension/compensation never prove caregiver enrollment.
        enrolled = False
    if enrolled:
        return True, f"{profile_program_label(doc_key)} is already active for the care recipient, so they are eligible.", _ENROLLED_MATCH_LEVEL
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
    available, value = known_fact(profile, "care_recipient.state")
    state = (value or "").strip() if available else ""
    if state and state.upper() not in {"CA", "CALIFORNIA"}:
        return (
            True,
            f"IHSS is a California-only program (care recipient state: {state})",
            "none",
        )
    return False, "", "none"


def check_va(profile: CaseProfile) -> GateResult:
    """Only an explicit absence of military connection can rule this route out.

    Default False, VA health coverage, a pension, or compensation do not establish
    caregiver-program eligibility. Active medical-discharge cases need review too.
    """
    coverage = _norm(_evidence(profile, "care_recipient.health_coverage", "recipient.health_coverage"))
    benefits = _norm(_evidence(profile, "care_recipient.current_benefits", "recipient.current_benefits"))
    has_va_signal = "va health care" in coverage or any(v.startswith("va ") for v in benefits)
    if profile.answers.get("recipient.military_status") == "None of these" and not has_va_signal:
        return True, "No military connection was reported for the care recipient", "none"
    return False, "", "none"


def check_medicare(profile: CaseProfile) -> GateResult:
    """Existing Medicare is actionable; age alone cannot eliminate all pathways."""
    return check_enrolled(profile, "medicare")


def check_pfl(profile: CaseProfile) -> GateResult:  # noqa: ARG001
    """Covered wage history and leave facts need program review.

    Residence is not work state, and current unemployment/retirement does not prove
    absence of qualifying base-period wages or labor-market attachment at leave.
    """
    return False, "", "none"


def check_medical(profile: CaseProfile) -> GateResult:
    """Honor current coverage; do not invent an income ceiling or budget unit."""
    return check_enrolled(profile, "medical")


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
