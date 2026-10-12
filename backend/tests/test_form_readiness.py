"""Tests for form-readiness: the eligibility→forms context bridge.

Verifies the pure projection reuses persisted specialist findings, filters out
non-actionable ('none') programs, orders strongest-first, and carries the deferred
sensitive-field set forms will need. No LLM / Durable runtime involved.
"""

from __future__ import annotations

from app.forms.readiness import program_readiness
from app.intake.schema import DELAYED_QUESTIONS
from app.models import CaseProfile, EligibilityResult


def _profile_with_results(*results: EligibilityResult) -> CaseProfile:
    p = CaseProfile(id="t")
    for r in results:
        p.eligibility[r.program] = r
    return p


def test_reuses_specialist_documents_and_gaps():
    p = _profile_with_results(
        EligibilityResult(
            program="IHSS",
            match_level="very_likely",
            status="likely",
            required_documents=["Medi-Cal card", "SOC 873 physician certification"],
            missing_info=["Dolores's Medi-Cal ID", "household income breakdown"],
            next_steps=["Contact Fresno County IHSS office"],
        )
    )
    readiness = program_readiness(p)
    assert len(readiness) == 1
    r = readiness[0]
    assert r.program == "IHSS"
    assert "SOC 873 physician certification" in r.required_documents
    assert "household income breakdown" in r.missing_info
    assert r.next_steps == ["Contact Fresno County IHSS office"]
    # Withheld set is carried so the forms flow knows what intake deferred.
    assert "Social Security number" in r.withheld_fields
    assert r.withheld_fields == list(DELAYED_QUESTIONS)


def test_none_match_programs_are_excluded():
    p = _profile_with_results(
        EligibilityResult(program="VA Caregiver Support", match_level="none", status="unlikely"),
        EligibilityResult(program="Medi-Cal", match_level="very_likely", status="likely"),
    )
    readiness = program_readiness(p)
    programs = [r.program for r in readiness]
    assert "VA Caregiver Support" not in programs
    assert "Medi-Cal" in programs


def test_ordered_strongest_first():
    p = _profile_with_results(
        EligibilityResult(program="Tax", match_level="low", status="unlikely"),
        EligibilityResult(program="PFL", match_level="likely", status="likely"),
        EligibilityResult(program="Medi-Cal", match_level="very_likely", status="likely"),
    )
    order = [r.match_level for r in program_readiness(p)]
    assert order == ["very_likely", "likely", "low"]


def test_empty_before_eligibility_completes():
    assert program_readiness(CaseProfile(id="t")) == []
