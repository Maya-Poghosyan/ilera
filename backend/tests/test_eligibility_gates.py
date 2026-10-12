"""Tests for the deterministic eligibility gates.

Focus: a program the care recipient explicitly reports currently receiving must be
reported as eligible (match_level="very_likely"), not as "not eligible". This covers
the bug where someone already on Medicaid/Medi-Cal was shown as ineligible.

These tests exercise the pure-Python gate functions directly — no LLM, no Durable
runtime, no pydantic_ai required.
"""

from __future__ import annotations

from app.intake.mapping import map_answers_to_profile
from app.models import CaseProfile
from durable.tools.eligibility_checks import (
    check_enrolled,
    check_medical,
    check_medicare,
    check_pfl,
    check_va,
    make_gate_tool,
)


def _profile(**care_recipient_fields) -> CaseProfile:
    p = CaseProfile(id="t")
    for k, v in care_recipient_fields.items():
        setattr(p.care_recipient, k, v)
    return p


# ── Regression: the gate tool's type hints must resolve at runtime ────────────
#
# pydantic-ai builds a tool schema by calling typing.get_type_hints() on the tool
# function. If `RunContext` is not a resolvable name in the module's runtime globals
# (e.g. it was imported only under TYPE_CHECKING), that call raises
# `NameError: name 'RunContext' is not defined` and EVERY specialist that actually runs
# fails its assessment — silently rendering as "not eligible". This test exercises that
# exact call so the regression can never return without pydantic_ai installed.


def test_gate_tool_type_hints_resolve_at_runtime():
    import typing

    import durable.tools.eligibility_checks as mod

    # In production `from pydantic_ai import RunContext` makes RunContext a real Generic
    # class. Where pydantic_ai is absent it falls back to Any. Either way the tool's
    # annotation must resolve. Inject a Generic stub matching RunContext's shape when the
    # real class isn't present, mirroring the production import state.
    if getattr(mod.RunContext, "__class_getitem__", None) is None:
        T = typing.TypeVar("T")

        class _RunContextStub(typing.Generic[T]):
            pass

        original = mod.RunContext
        mod.RunContext = _RunContextStub
        try:
            hints = typing.get_type_hints(make_gate_tool("ihss"))
        finally:
            mod.RunContext = original
    else:
        hints = typing.get_type_hints(make_gate_tool("ihss"))

    assert "ctx" in hints  # resolved without NameError
    assert hints["return"] is str


# ── check_enrolled ──────────────────────────────────────────────────────────


def test_medical_insurance_marks_enrolled():
    skip, reason, level = check_enrolled(_profile(insurance="medi-cal"), "medical")
    assert skip is True
    assert level == "very_likely"
    assert "Medi-Cal" in reason


def test_medical_enrolled_now_answer_marks_enrolled():
    p = CaseProfile(id="t")
    p.answers = {"recipient.medicaid_status": "Enrolled now"}
    skip, _, level = check_enrolled(p, "medical")
    assert skip is True
    assert level == "very_likely"


def test_medical_health_coverage_medicaid_marks_enrolled():
    p = CaseProfile(id="t")
    p.answers = {"recipient.health_coverage": ["Medicaid"]}
    skip, _, level = check_enrolled(p, "medical")
    assert skip is True and level == "very_likely"


def test_medicare_coverage_marks_enrolled():
    p = CaseProfile(id="t")
    p.answers = {"recipient.health_coverage": ["Both Medicare and Medicaid"]}
    assert check_enrolled(p, "medicare")[2] == "very_likely"
    assert check_enrolled(p, "medical")[2] == "very_likely"


def test_va_benefit_marks_enrolled_but_bare_veteran_does_not():
    enrolled = _profile(current_benefits=["VA disability compensation"])
    assert check_enrolled(enrolled, "va")[2] == "very_likely"

    # A bare veteran flag is "potentially eligible", not enrolled → let specialist run.
    bare = _profile(veteran=True)
    assert check_enrolled(bare, "va")[0] is False


def test_no_enrollment_signal_does_not_skip():
    p = _profile(insurance="unknown")
    assert check_enrolled(p, "medical")[0] is False
    assert check_enrolled(p, "medicare")[0] is False
    assert check_enrolled(p, "va")[0] is False


# ── gate wiring: enrolled short-circuits before disqualification ──────────────


def test_check_medical_enrolled_beats_high_income_ceiling():
    """Someone already on Medi-Cal is eligible even if reported income is sky-high."""
    p = CaseProfile(id="t")
    p.care_recipient.insurance = "medi-cal"
    p.household.income_monthly = 999_999.0
    p.household.size = 1
    skip, reason, level = check_medical(p)
    assert skip is True
    assert level == "very_likely"  # not disqualified by the income ceiling
    assert "already active" in reason


def test_check_medical_high_income_still_disqualifies_when_not_enrolled():
    p = CaseProfile(id="t")
    p.household.income_monthly = 999_999.0
    p.household.size = 1
    skip, _, level = check_medical(p)
    assert skip is True
    assert level == "none"


def test_check_medicare_enrolled_short_circuits_very_likely():
    p = CaseProfile(id="t")
    p.answers = {"recipient.health_coverage": ["Medicare"]}
    skip, _, level = check_medicare(p)
    assert skip is True and level == "very_likely"


def test_check_va_enrolled_overrides_non_veteran_skip():
    """A VA health-care signal makes VA eligible even if `veteran` is unset/False."""
    p = CaseProfile(id="t")
    p.answers = {"recipient.health_coverage": ["VA health care"]}
    skip, _, level = check_va(p)
    assert skip is True and level == "very_likely"


def test_check_va_non_veteran_still_disqualifies():
    p = CaseProfile(id="t")  # veteran defaults False, no VA signals
    skip, _, level = check_va(p)
    assert skip is True and level == "none"


# ── end-to-end: real intake answers → mapped profile → gate ───────────────────


def test_full_intake_medicaid_enrolled_is_eligible():
    """Mirror the reported bug: a recipient who marks Medicaid 'Enrolled now' and lists
    Medicaid coverage must gate to very_likely for Medi-Cal."""
    answers = {
        "recipient.first_name": "Pat",
        "recipient.medicaid_status": "Enrolled now",
        "recipient.health_coverage": ["Medicaid"],
        "recipient.monthly_income_range": "$5,000 or more",
    }
    profile = map_answers_to_profile(answers, CaseProfile(id="t"))

    # mapping should derive medi-cal insurance from the answers
    assert profile.care_recipient.insurance == "medi-cal"

    skip, _, level = check_medical(profile)
    assert skip is True
    assert level == "very_likely"


# ── check_pfl: corrected deterministic skips ──────────────────────────────────


def _pfl_profile(status: str = "", state: str = "CA") -> CaseProfile:
    p = CaseProfile(id="t")
    p.caregiver.employment_status = status
    p.caregiver.state = state
    return p


def test_pfl_in_state_unemployed_is_skipped():
    """Regression: an unemployed CA caregiver has no SDI wages — must skip (prior logic
    only skipped when ALSO out of state, wasting an LLM call)."""
    skip, reason, level = check_pfl(_pfl_profile(status="Unemployed", state="CA"))
    assert skip is True and level == "none"
    assert "SDI" in reason


def test_pfl_in_state_retired_is_skipped():
    skip, _, level = check_pfl(_pfl_profile(status="Retired", state="CA"))
    assert skip is True and level == "none"


def test_pfl_out_of_state_is_skipped():
    skip, reason, level = check_pfl(_pfl_profile(status="Employed full time", state="TX"))
    assert skip is True and level == "none"
    assert "California" in reason


def test_pfl_self_employed_is_not_skipped():
    """Self-employed can opt into SDI via DIEC — conservative: let the specialist decide."""
    skip, _, _ = check_pfl(_pfl_profile(status="Self-employed", state="CA"))
    assert skip is False


def test_pfl_employed_in_ca_is_not_skipped():
    skip, _, _ = check_pfl(_pfl_profile(status="Employed full time", state="CA"))
    assert skip is False


def test_pfl_unknown_status_in_ca_is_not_skipped():
    skip, _, _ = check_pfl(_pfl_profile(status="", state="CA"))
    assert skip is False
