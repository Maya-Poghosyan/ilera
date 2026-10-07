"""Typed I/O contracts between the Durable orchestrator and its activities.

Kept separate from app/models.py so the Function App can import them without
pulling in FastAPI or SQLAlchemy. All fields that can carry failure information
use the error record types from errors.py.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MatchLevel = Literal["none", "low", "medium", "likely", "very_likely", "assessment_failed"]


# ── Inputs ─────────────────────────────────────────────────────────────────────


class CaseInput(BaseModel):
    """What the orchestrator receives when triggered via HTTP starter."""
    case_id: str
    profile_json: str  # serialized CaseProfile; deserialized once, passed to activities


class EligibilityGateInput(BaseModel):
    doc_key: str
    profile_json: str


class SpecialistInput(BaseModel):
    doc_key: str
    profile_json: str
    # Answers from peer queries resolved by the orchestrator before this run.
    # Key: target doc_key, value: PeerQueryResult.
    peer_answers: dict[str, "PeerQueryResult"] = Field(default_factory=dict)


class PeerQueryInput(BaseModel):
    asking_doc_key: str
    target_doc_key: str
    # The natural-language question the asking specialist needs answered.
    question: str
    profile_json: str


class SynthesisInput(BaseModel):
    case_id: str
    profile_json: str
    specialist_results: list["SpecialistResult"]


# ── Outputs ────────────────────────────────────────────────────────────────────


class EligibilityGateResult(BaseModel):
    doc_key: str
    # True = deterministic check found a clear disqualification; skip the LLM activity.
    skip: bool
    # Human-readable reason shown in the specialist's finding when skip=True.
    reason: str = ""
    # Pre-computed level used as the finding when skip=True (almost always "none").
    fast_match_level: MatchLevel = "none"
    # Set when the gate function itself raised an unexpected exception.
    # The orchestrator treats gate_error as skip=False (conservative: let specialist run).
    gate_error: dict[str, Any] | None = None


class PeerQueryResult(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    # Set when the peer target's activity failed; the asking specialist proceeds
    # without the answer and this record explains the gap.
    peer_error: dict[str, Any] | None = None


class SpecialistResult(BaseModel):
    doc_key: str
    program: str
    match_level: MatchLevel
    notes: list[str] = Field(default_factory=list)
    cross_programs: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    # Full structured EligibilityResult for the applications page (JSON string).
    eligibility_result_json: str = ""
    # Set when the LLM call failed; match_level will be "assessment_failed".
    error_record: dict[str, Any] | None = None

    @property
    def fully_failed(self) -> bool:
        return self.match_level == "assessment_failed"


class SynthesisResult(BaseModel):
    strategy: str
    interaction_notes: list[str] = Field(default_factory=list)
    # Non-empty when one or more specialists had error records — surfaced to the
    # frontend so it can warn the caregiver that some programs could not be assessed.
    failed_specialist_programs: list[str] = Field(default_factory=list)
