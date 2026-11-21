"""Bounded model outputs; brevity is validated, never achieved by truncating facts."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ShortText = Annotated[str, Field(min_length=1, max_length=180)]


class CompactOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _check_words(parts: list[str], limit: int) -> None:
    if sum(len(part.split()) for part in parts) > limit:
        raise ValueError(f"Use at most {limit} words; prioritize decision-changing facts and actions.")


class FollowupOutput(CompactOutput):
    id: str = Field(min_length=1, max_length=80)
    prompt: ShortText
    type: Literal["short_text", "long_text", "select", "multiselect", "boolean"] = "short_text"
    options: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(default_factory=list, max_length=12)
    why: str = Field(default="", max_length=160)


class SpecialistOutput(CompactOutput):
    """Stable eligibility shape, with at most 220 words of caregiver-facing prose."""
    match_level: Literal["none", "low", "medium", "likely", "very_likely"]
    summary: str = Field(min_length=1, max_length=240, description="One plain-language sentence about this case; no citations or program overview.")
    roadblocks: list[ShortText] = Field(default_factory=list, max_length=3)
    next_steps: list[ShortText] = Field(default_factory=list, max_length=3)
    required_documents: list[ShortText] = Field(default_factory=list, max_length=4)
    missing_info: list[ShortText] = Field(default_factory=list, max_length=3)
    followups: list[FollowupOutput] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def concise(self) -> SpecialistOutput:
        _check_words([self.summary, *self.roadblocks, *self.next_steps,
                      *self.required_documents, *self.missing_info,
                      *(part for f in self.followups for part in [f.prompt, f.why, *f.options])], 220)
        return self


class EvidenceRef(CompactOutput):
    document_id: str = Field(min_length=1, max_length=256)
    # The corpus stores page labels as strings (including ranges and "").
    page: str = Field(max_length=80)


class ResearchFinding(CompactOutput):
    finding: str = Field(min_length=1, max_length=280, description="One decision-changing finding; at most 15 words.")
    citations: list[EvidenceRef] = Field(min_length=1, max_length=3)


class ResearchAnswer(CompactOutput):
    """A decision, up to three cited findings, actions and explicit evidence gaps."""
    conclusion: str = Field(min_length=1, max_length=240, description="One decision or next action, at most 15 words.")
    findings: list[ResearchFinding] = Field(default_factory=list, max_length=3)
    next_steps: list[ShortText] = Field(default_factory=list, max_length=3, description="At most 10 words per step; use fewer than three when sufficient.")
    limitations: list[ShortText] = Field(default_factory=list, max_length=2, description="Only material evidence gaps, at most 15 words each.")

    @model_validator(mode="after")
    def concise(self) -> ResearchAnswer:
        _check_words([self.conclusion, *(f.finding for f in self.findings),
                      *self.next_steps, *self.limitations], 150)
        return self

    def validate_evidence(self, evidence: list[dict]) -> None:
        available = {(h.get("document_id") or h["source"], h.get("page")) for h in evidence}
        for finding in self.findings:
            if any((ref.document_id, ref.page) not in available for ref in finding.citations):
                raise ValueError("Research citations must match a supplied document and page.")


class StrategyOutput(CompactOutput):
    bullets: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(max_length=7)

    @model_validator(mode="after")
    def concise(self) -> StrategyOutput:
        if any("\n" in bullet or "\r" in bullet for bullet in self.bullets):
            raise ValueError("Each strategy item must be one line.")
        _check_words(self.bullets, 180)
        return self


class InteractionOutput(CompactOutput):
    note: ShortText
    programs: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(min_length=2, max_length=6)
    action: str = Field(max_length=180)
    source_titles: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(min_length=1, max_length=3)


class InteractionsOutput(CompactOutput):
    interactions: list[InteractionOutput] = Field(max_length=3)

    @model_validator(mode="after")
    def concise(self) -> InteractionsOutput:
        _check_words([p for item in self.interactions for p in [item.note, item.action]], 150)
        return self


class ReportItem(CompactOutput):
    point: str = Field(min_length=1, max_length=200, description="One point that answers the question; at most 25 words.")
    programs: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(min_length=1, max_length=6)
    citations: list[EvidenceRef] = Field(min_length=1, max_length=4)


class ResearchReport(CompactOutput):
    """The answer to a research question: one merged list plus an optional short note."""
    items: list[ReportItem] = Field(min_length=1, max_length=8)
    note: str = Field(default="", max_length=300, description="Optional; at most 40 words; only what changes how to read the list.")

    @model_validator(mode="after")
    def concise(self) -> ResearchReport:
        for item in self.items:
            _check_words([item.point], 25)
        _check_words([self.note], 40)
        _check_words([self.note, *(i.point for i in self.items)], 220)
        return self

    def validate_citations(self, allowed: set[tuple[str, str]]) -> None:
        if any((ref.document_id, ref.page) not in allowed for item in self.items for ref in item.citations):
            raise ValueError("Cite only document/page pairs the specialists cited.")

    def markdown(self, question: str) -> str:
        lines = [f"**{question}**", ""]
        for item in self.items:
            refs = "; ".join(f"{r.document_id}" + (f" p. {r.page}" if r.page else "") for r in item.citations)
            lines.append(f"- {item.point} _({', '.join(item.programs)} — {refs})_")
        if self.note:
            lines += ["", self.note]
        return "\n".join(lines) + "\n"
