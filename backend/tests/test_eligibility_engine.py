import pytest

from app.models import CaseProfile
from app.eligibility.engine import evaluate_program
from app.eligibility.facts import write_fact
from app.eligibility.policy import ProgramPolicy
from app.eligibility.rules import evaluate_rule


def policy(*routes):
    return ProgramPolicy.model_validate({"program_id": "example", "ruleset_version": "test",
                                        "pathways": [{"pathway_id": str(i), "criteria": cs}
                                                     for i, cs in enumerate(routes)]})


def criterion(cid="residence", **updates):
    result = {"criterion_id": cid, "kind": "deterministic", "facts": ["care_recipient.state"],
              "rule": "care_recipient.state == 'CA'"}
    result.update(updates)
    return result


def test_default_and_explicit_evidence():
    profile = CaseProfile(id="engine")
    rules = policy([criterion()])
    assert evaluate_program(profile, rules).eligibility_status == "undetermined"
    write_fact(profile, "care_recipient.state", "CA")
    evaluation = evaluate_program(profile, rules)
    assert (evaluation.screening_status, evaluation.eligibility_status) == ("complete", "likely_eligible")
    assert evaluation.case_revision == profile.fact_revision
    write_fact(profile, "care_recipient.state", "NY")
    assert evaluate_program(profile, rules).eligibility_status == "likely_ineligible"


def test_remediable_condition_and_external_review():
    profile = CaseProfile(id="engine")
    write_fact(profile, "care_recipient.state", "NY", source_ref="answer:1")
    rules = policy([criterion(failure_effect="remediable"),
                    {"criterion_id": "county", "kind": "external", "external_note": "County review required"}])
    evaluation = evaluate_program(profile, rules)
    assert (evaluation.screening_status, evaluation.eligibility_status) == ("complete", "conditionally_eligible")
    assert evaluation.unresolved_criteria == ["residence", "county"]
    assert evaluation.evidence_refs == ["answer:1"]


def test_satisfied_route_ignores_unknown_alternative_and_eliminated_route():
    profile = CaseProfile(id="engine")
    write_fact(profile, "care_recipient.state", "CA")
    rules = policy([criterion()], [criterion("age", facts=["care_recipient.age"], rule="care_recipient.age >= 65")],
                   [criterion("other_state", rule="care_recipient.state == 'NY'")])
    evaluation = evaluate_program(profile, rules)
    assert evaluation.eligibility_status == "likely_eligible"
    assert evaluation.screening_status == "complete"
    assert not evaluation.unresolved_criteria
    assert evaluation.pathways[2].state == "eliminated"


def test_unknown_viable_route_prevents_ineligible_conclusion():
    profile = CaseProfile(id="engine")
    write_fact(profile, "care_recipient.state", "NY")
    evaluation = evaluate_program(profile, policy([criterion()], [criterion("age", facts=["care_recipient.age"], rule="care_recipient.age >= 65")]))
    assert evaluation.eligibility_status == "undetermined"
    assert evaluation.unresolved_criteria == ["age"]


def test_bucket_income_and_assisted_review_are_unknown():
    profile = CaseProfile(id="engine")
    write_fact(profile, "household.income_monthly", 750.0, precision="bucket")
    write_fact(profile, "care_recipient.care_needs", ["Bathing"])
    rules = policy([criterion("income", facts=["household.income_monthly"], rule="household.income_monthly < 1000"),
                    criterion("needs", kind="llm_assisted", facts=["care_recipient.care_needs"], rule=None,
                              policy_scope="example", question="Review needs")])
    evaluation = evaluate_program(profile, rules)
    assert evaluation.eligibility_status == "undetermined"
    assert [r.reason_code for r in evaluation.pathways[0].criteria] == ["insufficient_precision", "assisted_review_not_available"]


def test_interpreter_boolean_comparisons():
    assert evaluate_rule("care_recipient.age >= 65 and not (care_recipient.state in ['NY'])",
                         {"care_recipient.age": 70, "care_recipient.state": "CA"})


@pytest.mark.parametrize("rule", ["care_recipient", "not care_recipient.state", "care_recipient.state.lower() == 'ca'",
                                  "care_recipient.state == 'CA' or 'yes'", "care_recipient.state[0] == 'C'"])
def test_unsupported_rules_fail_validation(rule):
    with pytest.raises(ValueError):
        policy([criterion(rule=rule)])
