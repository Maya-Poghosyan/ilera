from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class CareRecipient(BaseModel):
    age: Optional[int] = None
    state: str = "CA"
    conditions: list[str] = Field(default_factory=list)
    veteran: bool = False
    insurance: Literal["medi-cal", "medicare", "private", "none", "unknown"] = "unknown"
    current_benefits: list[str] = Field(default_factory=list)
    care_needs: list[str] = Field(default_factory=list)


class Caregiver(BaseModel):
    relationship: str = ""
    employment_status: str = ""
    hours_per_week: Optional[int] = None


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


CaseProfile.model_rebuild()
