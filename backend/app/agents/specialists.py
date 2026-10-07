"""Specialist agent registry — maps doc_key and program name for the eligibility pipeline."""

from .base import SpecialistAgent


class IHSSAgent(SpecialistAgent):
    program = "IHSS"
    doc_key = "ihss"


class MediCalAgent(SpecialistAgent):
    program = "Medi-Cal"
    doc_key = "medical"


class PaidFamilyLeaveAgent(SpecialistAgent):
    program = "Paid Family Leave"
    doc_key = "pfl"


class VAAgent(SpecialistAgent):
    program = "VA Caregiver Support"
    doc_key = "va"


class MedicareAgent(SpecialistAgent):
    program = "Medicare"
    doc_key = "medicare"


class TaxAgent(SpecialistAgent):
    program = "Caregiver Tax Relief"
    doc_key = "tax"


ALL_SPECIALISTS: list[type[SpecialistAgent]] = [
    IHSSAgent,
    MediCalAgent,
    PaidFamilyLeaveAgent,
    VAAgent,
    MedicareAgent,
    TaxAgent,
]
