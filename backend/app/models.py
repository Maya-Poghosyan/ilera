from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class CareRecipient(BaseModel):
    name: str = ""
    date_of_birth: str = ""  # ISO date (YYYY-MM-DD)
    age: Optional[int] = None
    gender: str = ""
    state: str = "CA"
    street_address: str = ""
    city: str = ""
    zip_code: str = ""
    phone: str = ""
    email: str = ""
    ssn: str = ""  # stored only in-memory; never logged
    conditions: list[str] = Field(default_factory=list)
    veteran: bool = False
    insurance: Literal["medi-cal", "medicare", "private", "none", "unknown"] = "unknown"
    current_benefits: list[str] = Field(default_factory=list)
    care_needs: list[str] = Field(default_factory=list)


class Caregiver(BaseModel):
    name: str = ""
    relationship: str = ""
    employment_status: str = ""
    hours_per_week: Optional[int] = None
    phone: str = ""
    address: str = ""


class Household(BaseModel):
    size: Optional[int] = None
    income_monthly: Optional[float] = None
    assets: Optional[float] = None


class CaseProfile(BaseModel):
    """The shared spine of the app. Every agent reads and writes this object."""

    id: str
    care_recipient: CareRecipient = Field(default_factory=CareRecipient)
    caregiver: Caregiver = Field(default_factory=Caregiver)
    household: Household = Field(default_factory=Household)
    goals: list[str] = Field(default_factory=list)
    # Raw structured intake answers keyed by the schema's field_id (e.g.
    # "recipient.adl_needs"). This is the canonical record of what the user
    # entered; the typed fields above are projected from it via intake.mapping.
    answers: dict[str, Any] = Field(default_factory=dict)
    followups: dict[str, str] = Field(default_factory=dict)
    eligibility: dict[str, "EligibilityResult"] = Field(default_factory=dict)


class FollowupQuestion(BaseModel):
    program: str
    id: str
    prompt: str
    type: Literal["short_text", "long_text", "select", "multiselect", "boolean"] = "short_text"
    options: list[str] = Field(default_factory=list)
    why: str = ""


class Citation(BaseModel):
    """A reference to an official source document backing an agent's reasoning."""

    document_id: str = ""
    title: str = ""
    source_url: str = ""
    page: str = ""
    program: str = ""


class InteractionNote(BaseModel):
    """A cross-program eligibility interaction, grounded in inter-eligibility advising docs."""

    note: str = ""
    programs: list[str] = Field(default_factory=list)
    action: str = ""  # recommended sequencing / next step, if any
    citations: list[Citation] = Field(default_factory=list)


class EligibilityResult(BaseModel):
    program: str
    confidence: float = 0.0  # 0..1
    status: Literal["likely", "possible", "unlikely", "needs_info"] = "needs_info"
    rationale: str = ""
    roadblocks: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    followups: list[FollowupQuestion] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


CaseProfile.model_rebuild()
