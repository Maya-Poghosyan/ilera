"""Intake regressions: conditional branches, typed evidence and stale-data cleanup."""
from datetime import date

import pytest

from app.eligibility.facts import known_fact, write_fact
from app.intake.logic import QUESTIONS, answer_context, clean_answers, validate_answers, visible
from app.intake.mapping import map_answers_to_profile
from app.intake.schema import build_schema
from app.models import CaseProfile
from tests.intake_helpers import household_answers, member


def test_every_condition_references_a_real_question_or_computed_value():
    def refs(cond):
        if not cond: return set()
        if "field" in cond: return {cond["field"]}
        if "not" in cond: return refs(cond["not"])
        return set().union(*(refs(c) for c in cond.get("any", cond.get("all", []))))
    ids = [q["field_id"] for s in build_schema()["screens"] for q in s["questions"]]
    assert len(ids) == len(set(ids))
    derived = set(answer_context(household_answers(spouse={}))) | {
        "recipient.age", "caregiver.age", "recipient.health_coverage", "recipient.current_benefits",
        "recipient.claimed_as_dependent", "recipient.dependent_claimant_relationship"}
    for q in QUESTIONS.values():
        assert refs(q.get("show_when")) <= set(ids) | derived, q["field_id"]
    assert "mini_modules" not in build_schema()


def test_raw_answers_are_not_mutated_or_padded_with_legacy_fake_answers():
    answers = {"caregiver.coresidence": "Yes", "caregiver.address.state": "NY", "recipient.date_of_birth": "2000-05-01"}
    original = dict(answers)
    profile = map_answers_to_profile(answers, CaseProfile(id="intake"))
    assert answers == original
    assert profile.answers == original
    assert profile.care_recipient.state == "NY"
    assert "recipient.age" not in profile.answers
    assert "case.user_role" not in profile.answers
    assert profile.fact_metadata["care_recipient.state"].source_kind == "derived"


def test_clearing_birth_date_or_shared_address_clears_derived_evidence():
    profile = map_answers_to_profile({"recipient.date_of_birth": "2000-05-01", "caregiver.coresidence": "Yes", "caregiver.address.state": "NY"}, CaseProfile(id="intake"))
    assert profile.care_recipient.age is not None
    map_answers_to_profile({"recipient.date_of_birth": None, "caregiver.coresidence": "No"}, profile)
    assert known_fact(profile, "care_recipient.age") == (False, None)
    assert known_fact(profile, "care_recipient.state") == (False, None)


def test_hidden_values_cannot_survive_and_partial_updates_preserve_other_answers():
    answers = {**household_answers(), "case.has_applied_or_received": "Yes",
               "recipient.programs_touched": ["IHSS"], "recipient.program_statuses": {"IHSS": "Denied"},
               "case.program_dates": {"IHSS": "2025-01-01"}}
    profile = map_answers_to_profile(answers, CaseProfile(id="intake"))
    map_answers_to_profile({"case.has_applied_or_received": "No"}, profile)
    assert "recipient.program_statuses" not in profile.answers
    assert "case.program_dates" not in profile.answers
    assert profile.answers["household.members"] == answers["household.members"]


def test_explicit_unknown_clears_stale_fields_and_external_resolution_survives():
    profile = map_answers_to_profile({"recipient.adl_needs": ["Bathing or showering"], "recipient.coverage_and_benefits": ["SSI"]}, CaseProfile(id="intake"))
    map_answers_to_profile({"recipient.adl_needs": ["I'm not sure"], "recipient.coverage_and_benefits": ["No health coverage"]}, profile)
    assert known_fact(profile, "care_recipient.care_needs") == (False, None)
    assert known_fact(profile, "care_recipient.current_benefits") == (True, [])
    write_fact(profile, "care_recipient.state", "NY", source_ref="resolution:state")
    map_answers_to_profile({"recipient.address.state": "CA", "caregiver.coresidence": "No"}, profile)
    assert profile.care_recipient.state == "NY"


def test_invalid_typed_patch_is_atomic():
    profile = CaseProfile(id="intake")
    before = profile.model_dump()
    with pytest.raises(ValueError):
        map_answers_to_profile({"recipient.first_name": "New", "recipient.us_citizen": "invalid"}, profile)
    assert profile.model_dump() == before


def test_age_and_multi_select_followups_match_browser_contract():
    context = answer_context({"recipient.date_of_birth": "2004-10-13"}, date(2026, 10, 12))
    assert context["recipient.age"] == 21
    for key in ("caregiver.leave_start", "caregiver.sdi_deductions"):
        assert visible(QUESTIONS[key].get("show_when"), {"caregiver.caregiving_employment_impact": ["Taking leave"]})
        assert not visible(QUESTIONS[key].get("show_when"), {"caregiver.caregiving_employment_impact": ["Reduced hours"]})
        assert not visible(QUESTIONS[key].get("show_when"), {"caregiver.caregiving_employment_impact": ["No change"]})


@pytest.mark.parametrize("answers", [{"recipient.household_size": 0}, {"recipient.household_size": 1.5}, {"recipient.coverage_and_benefits": ["Medicare", "I'm not sure"]}, {"recipient.date_of_birth": "2026-02-30"}, {"recipient.onset_age": "Before age 18"}])
def test_server_rejects_invalid_or_obsolete_answers(answers):
    with pytest.raises(ValueError):
        validate_answers(answers)


def test_unsure_is_not_false_or_zero():
    answers = household_answers(recipient={"income_sources": ["I'm not sure"], "gross_monthly_income": "I'm not sure"})
    cleaned = validate_answers(answers)
    context = answer_context(cleaned)
    assert context["recipient.has_income"] is None
    assert context["household.reported_income_monthly"] is None
    assert clean_answers({"case.has_applied_or_received": "No", "recipient.program_statuses": {"IHSS": "Denied"}}) == {"case.has_applied_or_received": "No"}


def test_reported_income_never_becomes_a_guessed_eligibility_unit():
    answers = household_answers(recipient={"income_sources": ["Pension or retirement payments"], "gross_monthly_income": 1500})
    profile = map_answers_to_profile(answers, CaseProfile(id="intake"))
    assert known_fact(profile, "household.reported_income_monthly") == (True, 1500)
    assert known_fact(profile, "household.income_monthly") == (False, None)
    map_answers_to_profile(household_answers(), profile)
    assert known_fact(profile, "care_recipient.gross_monthly_income") == (True, 0)
    map_answers_to_profile(household_answers(recipient={"income_sources": ["I'm not sure"], "gross_monthly_income": "I'm not sure"}), profile)
    assert known_fact(profile, "household.reported_income_monthly") == (False, None)
    assert known_fact(profile, "care_recipient.gross_monthly_income") == (False, None)


def test_spouse_and_asset_branches_clear_when_parent_changes():
    answers = {**household_answers(spouse={"income_sources": ["Pension or retirement payments"], "gross_monthly_income": 900}),
        "recipient.spouse.assets": ["Savings or investments"], "recipient.spouse.assets_savings_investments": 5000,
        "recipient.spouse.assets_joint": "Yes", "recipient.spouse.assets_joint_details": "With spouse"}
    cleaned = clean_answers({**answers, "recipient.marital_status": "No"})
    assert not any(k.startswith("recipient.spouse.") for k in cleaned)
    assert not any(m["kind"] == "spouse" for m in cleaned["household.members"])
    cleaned = clean_answers({**answers, "recipient.spouse.assets": ["None"]})
    assert "recipient.spouse.assets_savings_investments" not in cleaned
    assert "recipient.spouse.assets_joint_details" not in cleaned
    assert answer_context(cleaned)["recipient.spouse.gross_monthly_income"] == 900


def test_medical_coverage_and_va_progression_do_not_depend_only_on_goals():
    answers = {"recipient.date_of_birth": "1980-01-01", "recipient.coverage_and_benefits": ["Medicare"], "recipient.military_status": "Veteran", "caregiver.coresidence": "No", "caregiver.relationship": "Friend"}
    context = answer_context(answers)
    for key in ["recipient.medicare_parts", "recipient.medicare_early_conditions", "recipient.va_health_enrolled", "caregiver.willing_va_coresidence"]:
        assert visible(QUESTIONS[key].get("show_when"), context)
    assert not visible(QUESTIONS["recipient.va_rating"].get("show_when"), context)
    assert not visible(QUESTIONS["recipient.va_service_start"].get("show_when"), context)
    assert visible(QUESTIONS["recipient.va_service_start"].get("show_when"), {**context, "recipient.va_pension_interest": "Yes"})


def test_known_no_income_requires_zero_and_unknown_does_not_mean_zero():
    with pytest.raises(ValueError):
        validate_answers(household_answers(recipient={"gross_monthly_income": 1234}))
    answers = validate_answers(household_answers(recipient={"income_sources": ["I'm not sure"], "gross_monthly_income": 0}))
    profile = map_answers_to_profile(answers, CaseProfile(id="unknown-income"))
    assert known_fact(profile, "household.reported_income_monthly") == (False, None)
    with pytest.raises(ValueError):
        validate_answers(household_answers(recipient={"income_sources": ["No income", "Wages"]}))


def test_household_members_reach_specialists_without_becoming_a_guessed_unit():
    other = member("other", "Parent", age="I'm not sure", lives_with_recipient=False,
                   tax_link="They claim the recipient", gross_monthly_income=2000,
                   income_sources=["Pension or retirement payments"])
    answers = household_answers(others=[other])
    profile = map_answers_to_profile(validate_answers(answers), CaseProfile(id="household-test"))
    assert profile.answers["household.members"][-1] == other
    assert profile.household.size == 2  # resident count excludes the nonresident parent
    assert profile.household.reported_income_monthly == 0
    assert profile.household.income_monthly is None
    from durable.activities.specialist import _build_user_prompt
    prompt = _build_user_prompt(profile, {})
    assert '"lives_with_recipient": false' in prompt
    assert 'They claim the recipient' in prompt
    for bad in [{**other, "age": 1.5}, {**other, "gross_monthly_income": -1}, {**other, "relationship": "Invalid"}, {**other, "ssn": "not allowed"}, {**other, "lives_with_recipient": None}]:
        with pytest.raises(ValueError):
            validate_answers(household_answers(others=[bad]))


def test_every_option_condition_uses_declared_values_and_array_operators():
    def conditions(c):
        if not c:
            return []
        if "field" in c:
            return [c]
        if "not" in c:
            return conditions(c["not"])
        return [leaf for child in c.get("any", c.get("all", [])) for leaf in conditions(child)]
    for question in QUESTIONS.values():
        for c in conditions(question.get("show_when")):
            target = QUESTIONS.get(c["field"])
            if not target or not target.get("options"):
                continue
            if c["op"] in {"answered", "blank"}:
                continue
            assert (c["op"] in {"includes", "includes_any"}) == (target["type"] in {"multi_select", "tag_input"}), (question["field_id"], c)
            choices = target["options"] + (["I'm not sure"] if target.get("allow_not_sure") else [])
            vals = c.get("value", [])
            vals = vals if isinstance(vals, list) else [vals]
            assert all(v in choices for v in vals), (question["field_id"], c)


def test_tax_and_future_ltc_followups_are_reachable():
    tax = answer_context(household_answers(caregiver={"income_sources": ["Wages"], "gross_monthly_income": 1000}))
    assert visible(QUESTIONS["tax.year"].get("show_when"), tax)
    assert visible(QUESTIONS["tax.adjusted_gross_income"]["show_when"], tax)
    assert not visible(QUESTIONS["tax.adjusted_gross_income"]["show_when"], answer_context(household_answers()))
    assert not visible(QUESTIONS["tax.paid_care_amount"]["show_when"], tax)
    assert visible(QUESTIONS["tax.paid_care_amount"]["show_when"], {**tax, "tax.paid_care_to_work": "Yes"})
    assert visible(QUESTIONS["recipient.recent_transfers"]["show_when"], {"recipient.planned_nursing_home": "Yes"})


def test_household_updates_propagate_employment_with_derived_provenance():
    answers = household_answers(caregiver={"employment_status": "Retired"}, spouse={
        "employment_status": "Employed full time", "income_sources": ["Wages"],
        "gross_monthly_income": 2000})
    profile = map_answers_to_profile(answers, CaseProfile(id="employment"))
    assert profile.caregiver.employment_status == "Retired"
    map_answers_to_profile({"caregiver.relationship": "Spouse or domestic partner"}, profile)
    assert profile.caregiver.employment_status == "Employed full time"
    assert profile.caregiver.gross_monthly_income == 2000
    assert profile.fact_metadata["caregiver.employment_status"].source_ref == "intake:household.members"
    assert profile.fact_metadata["caregiver.employment_status"].source_kind == "derived"
    assert not any(m["kind"] == "caregiver" for m in profile.answers["household.members"])
