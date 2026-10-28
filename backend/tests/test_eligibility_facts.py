"""Fact evidence must survive intake and never infer answers from defaults."""
import pytest

from app.eligibility.facts import known_fact, write_fact
from app.eligibility.policy import ProgramPolicy
from app.eligibility.loader import get_policy
from app.intake.mapping import map_answers_to_profile
from app.models import CaseProfile
from tests.intake_helpers import household_answers


def test_defaults_are_unknown_but_explicit_false_zero_and_empty_list_are_known():
    profile = CaseProfile(id="facts")
    assert known_fact(profile, "care_recipient.state") == (False, None)
    assert known_fact(profile, "care_recipient.veteran") == (False, None)
    for path, value in [("care_recipient.veteran", False), ("household.income_monthly", 0.0),
                        ("care_recipient.care_needs", [])]:
        write_fact(profile, path, value)
        assert known_fact(profile, path) == (True, value)
    assert CaseProfile.model_validate_json(profile.model_dump_json()).fact_revision == 3


def test_invalid_or_sensitive_write_does_not_mutate_case():
    profile = CaseProfile(id="facts")
    before = profile.model_dump()
    for path, value in [("recipient.living_setting", "Own home"),
                        ("care_recipient.ssn", "123"), ("care_recipient.veteran", "False"),
                        ("care_recipient.state", "")]:
        with pytest.raises(ValueError):
            write_fact(profile, path, value)
        assert profile.model_dump() == before


def test_intake_maps_reported_policy_inputs_idempotently():
    profile = CaseProfile(id="facts")
    answers = {"recipient.address.state": "CA", "recipient.living_setting": "Own home",
               "recipient.medicaid_covered": True,
               "recipient.coverage_and_benefits": ["Medicare", "Medicaid"],
               "recipient.adl_needs": ["None of these"],
               **household_answers(), "caregiver.coresidence": "No"}
    map_answers_to_profile(dict(answers), profile)
    revision = profile.fact_revision
    map_answers_to_profile(dict(answers), profile)
    assert profile.fact_revision == revision
    assert known_fact(profile, "care_recipient.medicaid_status") == (True, "Enrolled now")
    assert known_fact(profile, "care_recipient.care_needs") == (True, [])
    assert profile.fact_metadata["household.reported_income_monthly"].precision == "derived"
    assert known_fact(profile, "household.reported_income_monthly") == (True, 0.0)
    assert known_fact(profile, "household.income_monthly") == (False, None)


def test_skip_clears_evidence_and_later_intake_preserves_task_resolution():
    profile = CaseProfile(id="facts")
    map_answers_to_profile({"caregiver.coresidence": "No", "recipient.living_setting": "Own home"}, profile)
    map_answers_to_profile({"recipient.living_setting": "Prefer not to answer"}, profile)
    assert known_fact(profile, "care_recipient.living_setting") == (False, None)
    assert profile.fact_metadata["care_recipient.living_setting"].availability == "skipped"
    write_fact(profile, "care_recipient.living_setting", "Family member's home", source_ref="task:1")
    write_fact(profile, "care_recipient.state", "NY", source_ref="task:2")
    map_answers_to_profile({"recipient.living_setting": "Own home", "recipient.address.state": "CA"}, profile)
    assert known_fact(profile, "care_recipient.living_setting") == (True, "Family member's home")
    assert profile.care_recipient.state == "NY"


@pytest.mark.parametrize("mutation", ["bad_path", "call", "empty_pathway", "duplicate", "wrong_kind"])
def test_policy_rejects_invalid_contracts(mutation):
    data = get_policy("ihss").model_dump()
    criterion = data["pathways"][0]["criteria"][0]
    if mutation == "bad_path":
        criterion["facts"] = ["recipient.address.state"]
    elif mutation == "call":
        criterion["rule"] = "__import__('os').system('anything')"
    elif mutation == "empty_pathway":
        data["pathways"][0]["criteria"] = []
    elif mutation == "duplicate":
        data["pathways"].append(data["pathways"][0])
    else:
        criterion["external_note"] = "Wrong kind"
    with pytest.raises(ValueError):
        ProgramPolicy.model_validate(data)


def test_changed_intake_fact_advances_revision_and_partial_update_preserves_evidence():
    profile = CaseProfile(id="facts")
    map_answers_to_profile({"caregiver.coresidence": "No", "recipient.address.state": "CA"}, profile)
    first_revision = profile.fact_revision
    map_answers_to_profile({"recipient.address.state": "NY"}, profile)
    assert profile.fact_revision == first_revision + 1
    assert known_fact(profile, "care_recipient.state") == (True, "NY")
    map_answers_to_profile({"recipient.adl_needs": ["Bathing"]}, profile)
    assert known_fact(profile, "care_recipient.state") == (True, "NY")
