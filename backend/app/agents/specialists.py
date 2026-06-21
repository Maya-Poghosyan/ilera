"""Specialist agents for individual benefit programs.

When an LLM key is configured, `SpecialistAgent.assess` uses grounded Claude reasoning
(see base.py). These `_heuristic_assess` bodies are the transparent no-key fallback.
"""

from ..models import CaseProfile, EligibilityResult, FollowupQuestion
from .base import SpecialistAgent


class IHSSAgent(SpecialistAgent):
    program = "IHSS"
    doc_key = "ihss"

    def _heuristic_assess(self, profile: CaseProfile) -> EligibilityResult:
        cr = profile.care_recipient
        on_medical = cr.insurance == "medi-cal"
        confidence = 0.7 if on_medical else 0.35
        status = "likely" if on_medical else "needs_info"
        return EligibilityResult(
            program=self.program,
            confidence=confidence,
            status=status,
            rationale=(
                "IHSS requires Medi-Cal eligibility and a need for in-home care."
                + (" Recipient is on Medi-Cal." if on_medical else " Medi-Cal status unconfirmed.")
            ),
            roadblocks=[] if on_medical else ["Confirm or establish Medi-Cal eligibility"],
            required_documents=["SOC 295 (application)", "Medi-Cal verification", "Proof of residency"],
            next_steps=["Apply for IHSS via county social services", "Schedule in-home assessment"],
            missing_info=[] if on_medical else ["Medi-Cal enrollment status"],
            followups=[
                FollowupQuestion(
                    program=self.program,
                    id="ihss_living_situation",
                    prompt="Does the care recipient live in their own home (not a facility)?",
                    type="boolean",
                    why="IHSS only covers care delivered in the recipient's own home.",
                )
            ],
            sources=self._sources("IHSS eligibility requirements"),
            citations=self._citations("IHSS eligibility requirements"),
        )


class MediCalAgent(SpecialistAgent):
    program = "Medi-Cal"
    doc_key = "medical"

    def _heuristic_assess(self, profile: CaseProfile) -> EligibilityResult:
        hh = profile.household
        income = hh.income_monthly
        if income is None:
            status, confidence = "needs_info", 0.4
        elif (hh.size or 1) and income < 1800 * (hh.size or 1):
            status, confidence = "likely", 0.75
        else:
            status, confidence = "possible", 0.5
        return EligibilityResult(
            program=self.program,
            confidence=confidence,
            status=status,
            rationale="Medi-Cal eligibility is primarily income-based against the federal poverty level.",
            roadblocks=[] if income is not None else ["Household income not provided"],
            required_documents=["Proof of income", "Proof of identity", "Proof of California residency"],
            next_steps=["Apply via Covered California / county", "Gather income documentation"],
            missing_info=[] if income is not None else ["Monthly household income", "Household size"],
            followups=[
                FollowupQuestion(
                    program=self.program,
                    id="medical_income",
                    prompt="What is your total monthly household income?",
                    type="short_text",
                    why="Income relative to household size determines Medi-Cal eligibility.",
                )
            ],
            sources=self._sources("Medi-Cal income eligibility"),
            citations=self._citations("Medi-Cal income eligibility"),
        )


class PaidFamilyLeaveAgent(SpecialistAgent):
    program = "Paid Family Leave"
    doc_key = "pfl"

    def _heuristic_assess(self, profile: CaseProfile) -> EligibilityResult:
        cg = profile.caregiver
        employed = "employ" in cg.employment_status.lower() or cg.employment_status.lower() in {"full-time", "part-time", "w2"}
        confidence = 0.7 if employed else 0.3
        status = "likely" if employed else "unlikely"
        return EligibilityResult(
            program=self.program,
            confidence=confidence,
            status=status,
            rationale="CA PFL pays wage replacement to employees who paid into SDI and take time to care for a family member.",
            roadblocks=[] if employed else ["PFL requires recent SDI-covered wages"],
            required_documents=["DE 2501F (claim form)", "Care recipient medical certification"],
            next_steps=["File a PFL claim with EDD", "Obtain medical certification"],
            missing_info=[] if employed else ["Caregiver employment / SDI contribution history"],
            followups=[
                FollowupQuestion(
                    program=self.program,
                    id="pfl_sdi",
                    prompt="Have you paid into State Disability Insurance (SDI) in the last 18 months?",
                    type="boolean",
                    why="PFL eligibility requires recent SDI-covered earnings.",
                )
            ],
            sources=self._sources("Paid Family Leave eligibility"),
            citations=self._citations("Paid Family Leave eligibility"),
        )


class VAAgent(SpecialistAgent):
    program = "VA Caregiver Support"
    doc_key = "va"

    def _heuristic_assess(self, profile: CaseProfile) -> EligibilityResult:
        veteran = profile.care_recipient.veteran
        confidence = 0.65 if veteran else 0.05
        status = "possible" if veteran else "unlikely"
        return EligibilityResult(
            program=self.program,
            confidence=confidence,
            status=status,
            rationale="VA caregiver programs require the care recipient to be an eligible veteran.",
            roadblocks=[] if veteran else ["Care recipient is not a veteran"],
            required_documents=["VA Form 10-10CG", "Veteran service verification"],
            next_steps=["Apply to the Program of Comprehensive Assistance for Family Caregivers"] if veteran else [],
            missing_info=[],
            followups=(
                [
                    FollowupQuestion(
                        program=self.program,
                        id="va_service_connected",
                        prompt="Does the veteran have a service-connected disability rating?",
                        type="boolean",
                        why="Comprehensive caregiver benefits depend on service-connected disability.",
                    )
                ]
                if veteran
                else []
            ),
            sources=self._sources("VA caregiver eligibility"),
            citations=self._citations("VA caregiver eligibility"),
        )


class MedicareAgent(SpecialistAgent):
    program = "Medicare"
    doc_key = "medicare"

    def _heuristic_assess(self, profile: CaseProfile) -> EligibilityResult:
        cr = profile.care_recipient
        age = cr.age or 0
        on_medicare = cr.insurance == "medicare" or age >= 65
        if on_medicare:
            status, confidence = "likely", 0.8
        elif age and age >= 60:
            status, confidence = "possible", 0.45
        else:
            status, confidence = "needs_info", 0.35
        return EligibilityResult(
            program=self.program,
            confidence=confidence,
            status=status,
            rationale=(
                "Medicare covers people 65+ or those receiving SSDI for 24+ months; "
                "caregiver-relevant pieces include hospice respite and care coordination (PACE/GUIDE)."
            ),
            roadblocks=[] if on_medicare else ["Confirm Medicare entitlement (age 65+ or 24 months of SSDI)"],
            required_documents=["Medicare card or application", "Proof of age or disability"],
            next_steps=[
                "Review Medicare hospice respite and care-coordination options",
                "Check eligibility for PACE or the GUIDE dementia program",
            ],
            missing_info=[] if (cr.age is not None) else ["Care recipient age", "Medicare enrollment status"],
            followups=[
                FollowupQuestion(
                    program=self.program,
                    id="medicare_enrolled",
                    prompt="Is the care recipient currently enrolled in Medicare (Part A/B)?",
                    type="boolean",
                    why="Medicare enrollment unlocks hospice respite and care-coordination benefits.",
                )
            ],
            sources=self._sources("Medicare eligibility hospice respite"),
            citations=self._citations("Medicare eligibility hospice respite"),
        )


class TaxAgent(SpecialistAgent):
    program = "Caregiver Tax Relief"
    doc_key = "tax"

    def _heuristic_assess(self, profile: CaseProfile) -> EligibilityResult:
        provides_home = profile.caregiver.relationship != ""
        return EligibilityResult(
            program=self.program,
            confidence=0.5 if provides_home else 0.4,
            status="possible",
            rationale=(
                "Family caregivers may qualify for the Credit for Other Dependents, the "
                "Child & Dependent Care Credit, and medical-expense deductions; IHSS/Medicaid "
                "waiver payments to a live-in provider may be excludable under IRS Notice 2014-7."
            ),
            roadblocks=[],
            required_documents=["Prior-year tax return", "Records of medical & care expenses paid"],
            next_steps=[
                "Check whether the care recipient qualifies as a dependent",
                "Track deductible medical/care expenses",
                "If a live-in IHSS provider, review Notice 2014-7 income exclusion",
            ],
            missing_info=["Whether caregiver provides >half of recipient's support"],
            followups=[
                FollowupQuestion(
                    program=self.program,
                    id="tax_dependent_support",
                    prompt="Do you provide more than half of the care recipient's financial support?",
                    type="boolean",
                    why="Providing over half of support is a key test for claiming them as a dependent.",
                )
            ],
            sources=self._sources("dependent care credit medical expense deduction caregiver"),
            citations=self._citations("dependent care credit medical expense deduction caregiver"),
        )


ALL_SPECIALISTS: list[type[SpecialistAgent]] = [
    IHSSAgent,
    MediCalAgent,
    PaidFamilyLeaveAgent,
    VAAgent,
    MedicareAgent,
    TaxAgent,
]
