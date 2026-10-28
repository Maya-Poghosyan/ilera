"""Tests for the eligibility policy models and their file-fallback loader.

These run without a database: the loader falls back to the bundled JSON seeds in
data/program_policies/, so this verifies the authored policy validates against the
Pydantic model and the fact vocabulary is profile_path-keyed.
"""

from __future__ import annotations

from app.eligibility.loader import get_policy, list_policies
from app.eligibility.policy import ProgramPolicy


def test_ihss_seed_loads_and_validates():
    p = get_policy("ihss")
    assert p is not None
    assert p.program_id == "ihss"
    assert p.ruleset_version
    assert p.pathways, "IHSS policy should declare at least one pathway"


def test_criteria_declare_evaluation_kinds():
    p = get_policy("ihss")
    kinds = {c.kind for c in p.all_criteria()}
    # The hybrid model: deterministic + llm_assisted + external all present in IHSS.
    assert "deterministic" in kinds
    assert "llm_assisted" in kinds
    assert "external" in kinds


def test_facts_are_profile_paths():
    """Every fact a criterion depends on is addressed by a CaseProfile profile_path,
    so a resolved fact also feeds form autocompletion."""
    from app.eligibility.facts import fact_registry

    legal = set(fact_registry())
    p = get_policy("ihss")
    for crit in p.all_criteria():
        for fact in crit.facts:
            assert fact in legal, f"{crit.criterion_id}: unknown canonical path {fact!r}"



def test_llm_assisted_criteria_carry_scope_and_question():
    p = get_policy("ihss")
    for crit in p.all_criteria():
        if crit.kind == "llm_assisted":
            assert crit.policy_scope, f"{crit.criterion_id} must name a policy_scope"
            assert crit.question, f"{crit.criterion_id} must pose a question"


def test_deterministic_criteria_carry_a_rule():
    p = get_policy("ihss")
    for crit in p.all_criteria():
        if crit.kind == "deterministic":
            assert crit.rule, f"{crit.criterion_id} must carry a rule expression"


def test_external_criteria_never_require_user_facts_to_satisfy():
    p = get_policy("ihss")
    externals = [c for c in p.all_criteria() if c.kind == "external"]
    assert externals, "IHSS has a county-assessment external criterion"
    for crit in externals:
        assert crit.external_note, f"{crit.criterion_id} should explain the external step"


def test_list_policies_returns_the_seed():
    policies = list_policies()
    assert any(p.program_id == "ihss" for p in policies)
    assert all(isinstance(p, ProgramPolicy) for p in policies)
