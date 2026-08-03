from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class CareRecipient(BaseModel):
    name: str = ""  # first and last together, for prose
    first_name: str = ""
    last_name: str = ""
    date_of_birth: str = ""  # ISO date (YYYY-MM-DD)
    age: Optional[int] = None
    gender: str = ""
    state: str = "CA"
    street_address: str = ""
    city: str = ""
    county: str = ""
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
    name: str = ""  # first and last together, for prose
    first_name: str = ""
    last_name: str = ""
    relationship: str = ""
    employment_status: str = ""
    hours_per_week: Optional[int] = None
    phone: str = ""
    email: str = ""
    address: str = ""  # state and ZIP, as the eligibility agents have always read it
    street_address: str = ""
    city: str = ""
    state: str = "CA"
    county: str = ""
    zip_code: str = ""


class Household(BaseModel):
    size: Optional[int] = None
    income_monthly: Optional[float] = None


# Five-level eligibility match scale produced by each Band specialist agent.
MatchLevel = Literal["none", "low", "medium", "likely", "very_likely"]

# Lifecycle of a case's Band eligibility run.
BandStatus = Literal["idle", "processing", "complete", "error"]


class SpecialistFinding(BaseModel):
    """A single specialist agent's complete eligibility determination for its program,
    submitted back to the routing agent via the Band `submit_complete_response` tool."""

    program: str = ""
    doc_key: str = ""
    match_level: MatchLevel = "none"
    notes: list[str] = Field(default_factory=list)  # a few notes explaining the determination
    cross_programs: list[str] = Field(default_factory=list)  # peers flagged for cross-eligibility
    citations: list[str] = Field(default_factory=list)  # "Title (page) — URL" strings
    complete: bool = False
    updated_at: str = ""


class CaseProfile(BaseModel):
    """The shared spine of the app. Every agent reads and writes this object."""

    id: str
    care_recipient: CareRecipient = Field(default_factory=CareRecipient)
    caregiver: Caregiver = Field(default_factory=Caregiver)
    household: Household = Field(default_factory=Household)
    # Raw structured intake answers keyed by the schema's field_id (e.g.
    # "recipient.adl_needs"). This is the canonical record of what the user
    # entered; the typed fields above are projected from it via intake.mapping.
    answers: dict[str, Any] = Field(default_factory=dict)
    followups: dict[str, str] = Field(default_factory=dict)
    eligibility: dict[str, "EligibilityResult"] = Field(default_factory=dict)

    # --- Band eligibility orchestration ---------------------------------
    # One Band chat room per case; the routing + specialist agents coordinate here.
    band_chat_id: str = ""
    band_status: BandStatus = "idle"
    band_error: str = ""
    band_started_at: str = ""
    band_completed_at: str = ""
    # Specialist findings keyed by doc_key (ihss, medical, medicare, pfl, va, tax).
    findings: dict[str, SpecialistFinding] = Field(default_factory=dict)
    # doc_keys the routing agent @mentioned in the seed and expects a complete response from.
    expected_specialists: list[str] = Field(default_factory=list)
    # The routing agent's synthesized, human-facing application strategy.
    strategy: str = ""
    strategy_complete: bool = False
    # Set True right before the routing agent is asked to synthesize. The mention-gate keeps
    # routing silent (ignores specialist chatter) until this flips, so routing only acts once.
    synthesis_requested: bool = False
    # Per-specialist count of cross-eligibility peer messages sent via ask_peer this run. Bounds
    # the peer conversation: once a specialist hits the budget, ask_peer refuses further sends.
    peer_msg_counts: dict[str, int] = Field(default_factory=dict)


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
    match_level: MatchLevel = "none"  # the specialist's five-level determination
    rationale: str = ""
    roadblocks: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    followups: list[FollowupQuestion] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


CaseProfile.model_rebuild()
