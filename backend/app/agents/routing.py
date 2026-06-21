"""Routing agent.

Reads the CaseProfile and decides which specialist agents to activate, then runs them
and coordinates results through the shared agent space.
"""

from ..models import CaseProfile, EligibilityResult, FollowupQuestion, InteractionNote
from . import band_space
from .interactions import analyze_interactions
from .specialists import ALL_SPECIALISTS, SpecialistAgent


def select_specialists(profile: CaseProfile) -> list[SpecialistAgent]:
    """Pick specialists worth running. Cheap to run all four for the demo, but we still
    gate VA on veteran status to show routing behavior."""
    cr = profile.care_recipient
    age = cr.age or 0
    selected: list[SpecialistAgent] = []
    for cls in ALL_SPECIALISTS:
        agent = cls()
        if agent.program == "VA Caregiver Support" and not cr.veteran:
            continue
        # Medicare is age/disability based — skip only when clearly too young and not enrolled.
        if agent.program == "Medicare" and age and age < 60 and cr.insurance != "medicare":
            continue
        selected.append(agent)
    return selected


class RoutingResult:
    def __init__(
        self,
        results: list[EligibilityResult],
        followups: list[FollowupQuestion],
        strategy_notes: list[str],
        interaction_notes: list[InteractionNote] | None = None,
    ) -> None:
        self.results = results
        self.followups = followups
        self.strategy_notes = strategy_notes
        self.interaction_notes = interaction_notes or []


def run_routing(profile: CaseProfile) -> RoutingResult:
    specialists = select_specialists(profile)
    results = [a.assess(profile) for a in specialists]
    results.sort(key=lambda r: r.confidence, reverse=True)
    followups = band_space.dedupe_followups(results)
    interaction_notes = analyze_interactions(profile, results)
    notes = [n.note if not n.action else f"{n.note} {n.action}" for n in interaction_notes]
    return RoutingResult(
        results=results,
        followups=followups,
        strategy_notes=notes,
        interaction_notes=interaction_notes,
    )
