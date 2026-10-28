"""Pure shadow-mode eligibility evaluation; no model/network calls or legacy writes.

LLM and agency adapters are intentionally not wired yet. Their criteria remain
explicit unknown/external_pending rather than trusting old MatchLevel findings.
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from ..models import CaseProfile
from .facts import known_fact
from .policy import Criterion, ProgramPolicy
from .rules import evaluate_rule


class CriterionResult(BaseModel):
    criterion_id: str
    pathway_id: str
    state: Literal["satisfied", "not_satisfied", "unknown", "external_pending"]
    reason_code: str | None = None
    explanation: str
    consumed_fact_paths: list[str] = Field(default_factory=list)
    required_fact_paths: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    resolution_kind: Literal["user_fact", "prerequisite", "assessment", "review", "none"] = "none"


class PathwayResult(BaseModel):
    pathway_id: str
    state: Literal["satisfied", "eliminated", "conditional", "undetermined"]
    criteria: list[CriterionResult]


class ProgramEvaluation(BaseModel):
    program_id: str
    screening_status: Literal["complete", "incomplete"]
    eligibility_status: Literal["likely_eligible", "conditionally_eligible", "likely_ineligible", "undetermined"]
    case_revision: int
    ruleset_version: str
    evaluated_at: str
    pathways: list[PathwayResult]
    unresolved_criteria: list[str]
    explanation: str
    evidence_refs: list[str]


def _criterion(profile: CaseProfile, criterion: Criterion, pathway_id: str) -> CriterionResult:
    result = CriterionResult(
        criterion_id=criterion.criterion_id, pathway_id=pathway_id,
        state="unknown", explanation=criterion.description,
        consumed_fact_paths=criterion.facts,
    )
    if criterion.kind == "external":
        result.state = "external_pending"
        result.reason_code = "agency_determination_required"
        result.explanation = criterion.external_note or criterion.description
        result.resolution_kind = "assessment"
        return result
    values = {}
    for path in criterion.facts:
        available, value = known_fact(profile, path)
        metadata = profile.fact_metadata.get(path)
        if metadata and metadata.source_ref:
            result.evidence_refs.append(metadata.source_ref)
        if not available:
            result.required_fact_paths.append(path)
        else:
            values[path] = value
    if result.required_fact_paths:
        result.reason_code = "missing_or_unresolved_fact"
        result.resolution_kind = "user_fact"
        return result
    if criterion.kind == "llm_assisted":
        result.reason_code = "assisted_review_not_available"
        result.resolution_kind = "review"
    elif any(profile.fact_metadata[p].precision != "exact" for p in criterion.facts):
        # Conservative until policies declare which approximations their rules accept.
        result.required_fact_paths = [p for p in criterion.facts if profile.fact_metadata[p].precision != "exact"]
        result.reason_code = "insufficient_precision"
        result.resolution_kind = "user_fact"
    else:
        try:
            satisfied = evaluate_rule(criterion.rule, values)
            result.state = "satisfied" if satisfied else "not_satisfied"
            if not satisfied and criterion.failure_effect == "remediable":
                result.reason_code = "prerequisite_not_established"
                result.resolution_kind = "prerequisite"
        except (ValueError, TypeError, KeyError):
            result.reason_code = "rule_evaluation_error"
            result.resolution_kind = "review"
    return result


def evaluate_program(profile: CaseProfile, policy: ProgramPolicy) -> ProgramEvaluation:
    pathways = []
    for pathway in policy.pathways:
        criteria = [_criterion(profile, c, pathway.pathway_id) for c in pathway.criteria]
        eliminated = any(r.state == "not_satisfied" and c.failure_effect == "disqualifying"
                         for c, r in zip(pathway.criteria, criteria))
        if eliminated:
            state = "eliminated"
        elif all(r.state == "satisfied" for r in criteria):
            state = "satisfied"
        elif any(r.state == "unknown" for r in criteria):
            state = "undetermined"
        else:
            state = "conditional"
        pathways.append(PathwayResult(pathway_id=pathway.pathway_id, state=state, criteria=criteria))
    viable = [p for p in pathways if p.state != "eliminated"]
    if not viable:
        eligibility, screening, needed = "likely_ineligible", "complete", []
    elif any(p.state == "satisfied" for p in viable):
        eligibility, screening, needed = "likely_eligible", "complete", []
    else:
        conditional = [p for p in viable if p.state == "conditional"]
        needed = conditional or viable
        eligibility = "conditionally_eligible" if conditional else "undetermined"
        unresolved = [r for p in needed for r in p.criteria if r.state != "satisfied"]
        screening = ("incomplete" if any(r.state == "unknown" and r.resolution_kind == "user_fact"
                                             for r in unresolved) else "complete")
    reasons = {
        "likely_ineligible": "All authored pathways have a supported disqualifying criterion.",
        "likely_eligible": "An authored pathway is satisfied by the available evidence.",
        "conditionally_eligible": "A viable pathway has only prerequisite or agency conditions remaining.",
        "undetermined": "Available evidence is insufficient to support a preliminary conclusion.",
    }
    return ProgramEvaluation(
        program_id=policy.program_id, screening_status=screening,
        eligibility_status=eligibility, case_revision=profile.fact_revision,
        ruleset_version=policy.ruleset_version, evaluated_at=datetime.now(timezone.utc).isoformat(),
        pathways=pathways,
        unresolved_criteria=[r.criterion_id for p in needed for r in p.criteria if r.state != "satisfied"],
        explanation=reasons[eligibility],
        evidence_refs=sorted({ref for p in pathways for r in p.criteria for ref in r.evidence_refs}),
    )
