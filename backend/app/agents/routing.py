"""Routing agent.

Reads the CaseProfile and decides which specialist agents to activate, then runs them
and coordinates results through the shared agent space.
"""

from ..models import CaseProfile, EligibilityResult, FollowupQuestion
from . import band_space
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
    ) -> None:
        self.results = results
        self.followups = followups
        self.strategy_notes = strategy_notes


def run_routing(profile: CaseProfile) -> RoutingResult:
    specialists = select_specialists(profile)
    results = [a.assess(profile) for a in specialists]
    results.sort(key=lambda r: r.confidence, reverse=True)
    followups = band_space.dedupe_followups(results)
    notes = band_space.resolve_interactions(results)
    return RoutingResult(results=results, followups=followups, strategy_notes=notes)
