"""Eligibility policy models — the structured, authored description of what it takes
to qualify for a program.

A program's policy is a set of PATHWAYS, each a set of CRITERIA. Each criterion
declares HOW it is evaluated (`kind`), which keeps the facts-sacred / judgment-allowed
boundary enforceable rather than aspirational:

  deterministic  — a pure function over named profile_path facts. No LLM. Auditable.
  llm_assisted   — a judgment the LLM makes, but constrained: it sees only the named
                   `facts` (by profile_path) and the `policy_scope` corpus, and must
                   return a state + a citation. It cannot invent facts or policy.
  external       — only an agency can decide (county assessment, final determination).
                   Never satisfied by Ilera; surfaced as external_pending.

Facts are addressed by their CaseProfile `profile_path` (the same key the form filler
resolves against), so a fact resolved for a criterion is the same fact that
autocompletes a form. See docs/ilera_eligibility_action_planning_architecture.txt.

This is authored reference data: one ProgramPolicy per program, versioned by
`ruleset_version`, stored in the `reference.program_policies` table (seeded from the
bundled JSON files when the table is empty).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

CriterionKind = Literal["deterministic", "llm_assisted", "external"]


class Criterion(BaseModel):
    """One eligibility rule for a program, tagged with how it is evaluated."""

    criterion_id: str  # stable handle, e.g. "ihss.has_medi_cal"
    description: str = ""  # plain-language, for explanations and task titles

    kind: CriterionKind

    # CaseProfile profile_paths this criterion is evaluated against. The single fact
    # address shared with the form filler. For `external` criteria this may be empty.
    facts: list[str] = Field(default_factory=list)

    # deterministic: a declarative expression over `facts`, evaluated by the engine.
    # Kept as a string so the policy stays data; the engine owns the (safe) evaluator.
    rule: Optional[str] = None

    # llm_assisted: the program-scoped corpus the model may cite, and the question it
    # must answer. The model returns a state + citation; it may not invent either.
    policy_scope: Optional[str] = None
    question: Optional[str] = None

    # external: what the user is waiting on, surfaced in the explanation.
    external_note: Optional[str] = None
    failure_effect: Literal["disqualifying", "remediable"] = "disqualifying"

    @model_validator(mode="after")
    def validate_contract(self):
        from .facts import fact_registry
        from .rules import validate_rule

        if not self.criterion_id.strip():
            raise ValueError("criterion_id must be nonempty")
        if len(self.facts) != len(set(self.facts)) or any(f not in fact_registry() for f in self.facts):
            raise ValueError("Facts must be unique canonical persistent profile paths")
        if self.kind == "deterministic":
            if not self.rule or not self.facts:
                raise ValueError("Deterministic criteria require facts and a rule")
            validate_rule(self.rule, self.facts)
            if self.policy_scope or self.question or self.external_note:
                raise ValueError("Deterministic criterion has fields for another kind")
        elif self.kind == "llm_assisted":
            if not self.facts or not self.policy_scope or not self.question:
                raise ValueError("LLM criteria require facts, policy_scope and question")
            if self.rule or self.external_note:
                raise ValueError("LLM criterion has fields for another kind")
        elif not self.external_note or self.rule or self.question or self.policy_scope:
            raise ValueError("External criteria require only an external_note and optional facts")
        return self


class Pathway(BaseModel):
    """One route to qualifying for a program (e.g. standard IHSS vs. a waiver route).

    A pathway is satisfied when all its criteria are satisfied; a program is viable
    when any pathway is viable.
    """

    pathway_id: str
    description: str = ""
    criteria: list[Criterion] = Field(default_factory=list)


class ProgramPolicy(BaseModel):
    """The authored eligibility model for one program."""

    program_id: str  # matches the specialist doc_key, e.g. "ihss"
    program_name: str = ""
    ruleset_version: str = ""  # bump when the authored rules change
    pathways: list[Pathway] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_structure(self):
        if not self.program_id.strip() or not self.ruleset_version.strip() or not self.pathways:
            raise ValueError("Policy requires program_id, ruleset_version and pathways")
        ids = [p.pathway_id for p in self.pathways]
        if any(not i.strip() for i in ids) or len(ids) != len(set(ids)):
            raise ValueError("Pathway IDs must be nonempty and unique")
        if any(not p.criteria for p in self.pathways):
            raise ValueError("Pathways cannot be empty")
        criteria = [c.criterion_id for c in self.all_criteria()]
        if len(criteria) != len(set(criteria)):
            raise ValueError("Criterion IDs must be unique within a policy")
        return self

    def all_criteria(self) -> list[Criterion]:
        return [c for p in self.pathways for c in p.criteria]

    def fact_paths(self) -> set[str]:
        """Every profile_path any criterion depends on — the facts intake/screening
        must try to resolve for this program."""
        return {f for c in self.all_criteria() for f in c.facts}
