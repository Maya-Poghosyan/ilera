"""Immigration gates must be relevant, forward-reachable and safe on branch changes."""
from datetime import date, timedelta

import pytest

from app.intake.logic import QUESTIONS, answer_context, clean_answers, validate_answers, visible
from app.intake.mapping import map_answers_to_profile
from app.intake.schema import build_schema
from app.models import CaseProfile

from tests.intake_helpers import complete_current_intake

PAID = 'Get paid for caregiving'
MEDICAL = 'Find health coverage'
TAX = 'Get financial support or tax savings'


def shown(field, answers):
    return visible(QUESTIONS[field].get('show_when'), answer_context(answers))


def recipient(**patch):
    values = {'recipient.us_citizen': False, 'recipient.date_of_birth': '1950-01-01',
              'case.goals': [MEDICAL], 'recipient.medicaid_covered': False,
              'recipient.coverage_and_benefits': ['No health coverage'],
              'recipient.citizenship_residency': 'Lawful permanent resident',
              'recipient.medicare_insured_work': 'No'}
    values.update(patch)
    return values


def test_sections_and_prerequisites_are_encountered_before_followups():
    screens = build_schema()['screens']
    positions = {q['field_id']: (s, n) for s, screen in enumerate(screens) for n, q in enumerate(screen['questions'])}
    assert positions['case.goals'][0] == 2
    assert positions['caregiver.citizenship_residency'][0] == 3
    assert positions['caregiver.work_authorized'][0] == 3
    assert positions['caregiver.tax_residency'][0] == 3
    assert positions['recipient.citizenship_residency'][0] == 1
    assert positions['recipient.five_year_us_residence'][0] == 4
    immigration = ['caregiver.citizenship_residency', 'caregiver.work_authorized', 'caregiver.tax_residency',
                   'recipient.citizenship_residency', 'recipient.immigration_status_detail', 'recipient.lpr_since',
                   'recipient.five_year_us_residence', 'recipient.pregnancy_postpartum', 'recipient.foster_care_at_18',
                   'recipient.tax_residency']
    def refs(c):
        if not c: return []
        if 'field' in c: return [c['field']]
        if 'not' in c: return refs(c['not'])
        return [r for child in c.get('all', c.get('any', [])) for r in refs(child)]
    for field in immigration:
        for ref in refs(QUESTIONS[field]['show_when']):
            ref = {'recipient.age': 'recipient.date_of_birth', 'recipient.health_coverage': 'recipient.coverage_and_benefits'}.get(ref, ref)
            assert positions[ref] < positions[field], (field, ref)


@pytest.mark.parametrize('citizen', [True, "I'm not sure", 'Prefer not to answer', None])
def test_citizenship_unknown_and_citizens_do_not_trigger_status_probes(citizen):
    answers = {'caregiver.us_citizen': citizen, 'recipient.us_citizen': citizen,
               'case.goals': [PAID, MEDICAL, TAX], 'recipient.date_of_birth': '1950-01-01'}
    for field in ['caregiver.citizenship_residency', 'caregiver.work_authorized', 'caregiver.tax_residency',
                  'recipient.citizenship_residency', 'recipient.tax_residency']:
        assert not shown(field, answers)


def test_caregiver_work_and_tax_branches_are_independent():
    base = {'caregiver.us_citizen': False, 'caregiver.citizenship_residency': 'Another immigration status'}
    assert shown('caregiver.citizenship_residency', {**base, 'case.goals': [PAID]})
    assert shown('caregiver.work_authorized', {**base, 'case.goals': [PAID]})
    assert not shown('caregiver.tax_residency', {**base, 'case.goals': [PAID]})
    assert shown('caregiver.tax_residency', {**base, 'case.goals': [TAX]})
    assert not shown('caregiver.citizenship_residency', {**base, 'case.goals': [TAX]})
    assert not shown('caregiver.work_authorized', {**base, 'case.goals': [TAX]})
    assert not shown('caregiver.work_authorized', {**base, 'case.goals': [PAID], 'caregiver.citizenship_residency': 'Prefer not to answer'})
    # Taking leave/checking PFL alone never activates immigration questions.
    assert not shown('caregiver.citizenship_residency', {**base, 'caregiver.check_pfl': 'Yes'})
    assert not shown('caregiver.work_authorized', {**base, 'case.goals': ['Take a break from caregiving']})


def test_recipient_status_and_residence_gates_do_not_impose_blanket_five_year_rule():
    answers = recipient()
    assert shown('recipient.citizenship_residency', answers)
    assert shown('recipient.lpr_since', answers)
    assert shown('recipient.five_year_us_residence', answers)
    assert not shown('recipient.immigration_status_detail', answers)
    for work in ['Yes', None]:
        assert not shown('recipient.five_year_us_residence', {**answers, 'recipient.medicare_insured_work': work})
    assert not shown('recipient.five_year_us_residence', {**answers, 'recipient.coverage_and_benefits': ['Medicare']})
    assert not shown('recipient.five_year_us_residence', {**answers, 'recipient.date_of_birth': '1980-01-01'})
    child = {**answers, 'recipient.date_of_birth': '2015-01-01'}
    assert shown('recipient.citizenship_residency', child)
    assert shown('recipient.citizenship_residency', {**child, 'recipient.coverage_and_benefits': ['Medicare']})
    assert not shown('recipient.lpr_since', {**answers, 'recipient.medicaid_covered': True})
    other = {**answers, 'recipient.citizenship_residency': 'Another immigration status'}
    assert shown('recipient.immigration_status_detail', other)
    assert not shown('recipient.lpr_since', other)
    assert not shown('recipient.five_year_us_residence', other)


def test_combined_financial_goal_retains_tax_and_income_support_pathways():
    answers = recipient(**{'case.goals': [TAX]})
    assert shown('recipient.tax_residency', answers)
    assert shown('recipient.citizenship_residency', answers)
    assert shown('recipient.lpr_since', answers)


def test_medical_exceptions_are_age_gated_and_do_not_follow_a_declined_status():
    answers = recipient(**{'recipient.date_of_birth': '2005-01-01'})
    assert shown('recipient.pregnancy_postpartum', answers)
    assert shown('recipient.foster_care_at_18', answers)
    assert not shown('recipient.foster_care_at_18', recipient())
    assert not shown('recipient.pregnancy_postpartum', {**answers, 'recipient.medicaid_covered': True})
    assert not shown('recipient.pregnancy_postpartum', {**answers, 'recipient.citizenship_residency': 'Prefer not to answer'})


def test_branch_changes_clear_sensitive_answers_and_preserve_explicit_uncertainty():
    answers = {**recipient(), 'recipient.lpr_since': "I'm not sure", 'recipient.five_year_us_residence': 'Prefer not to answer',
               'caregiver.us_citizen': False, 'caregiver.citizenship_residency': 'Another immigration status',
               'caregiver.work_authorized': 'No', 'case.goals': [PAID, MEDICAL]}
    cleaned = validate_answers(answers)
    assert cleaned['recipient.lpr_since'] == "I'm not sure"
    assert cleaned['recipient.five_year_us_residence'] == 'Prefer not to answer'
    citizenship_change = clean_answers({**answers, 'caregiver.us_citizen': True, 'recipient.us_citizen': True})
    assert 'caregiver.work_authorized' not in citizenship_change
    assert 'recipient.lpr_since' not in citizenship_change
    assert 'recipient.five_year_us_residence' not in citizenship_change
    goal_change = clean_answers({**answers, 'case.goals': ['Take a break from caregiving']})
    assert 'caregiver.citizenship_residency' not in goal_change
    assert goal_change['recipient.citizenship_residency'] == 'Lawful permanent resident'
    profile = map_answers_to_profile(cleaned, CaseProfile(id='immigration'))
    assert profile.answers['caregiver.work_authorized'] == 'No'
    assert profile.answers['recipient.lpr_since'] == "I'm not sure"


def test_boolean_citizenship_requires_a_boolean_and_status_preserves_uncertainty():
    for key in ['caregiver.us_citizen', 'recipient.us_citizen']:
        with pytest.raises(ValueError):
            validate_answers({key: "I'm not sure"})
    values = {**recipient(), 'recipient.citizenship_residency': 'Prefer not to answer'}
    cleaned = validate_answers(values)
    profile = map_answers_to_profile(cleaned, CaseProfile(id='unknown'))
    assert profile.care_recipient.us_citizen is False
    assert profile.answers['recipient.citizenship_residency'] == 'Prefer not to answer'
    assert 'recipient.lpr_since' not in profile.answers


def test_future_lpr_dates_are_rejected_but_uncertainty_is_allowed():
    with pytest.raises(ValueError):
        validate_answers({**recipient(), 'recipient.lpr_since': (date.today() + timedelta(days=1)).isoformat()})
    assert validate_answers({**recipient(), 'recipient.lpr_since': 'Prefer not to answer'})['recipient.lpr_since'] == 'Prefer not to answer'




def test_complete_intake_api_retains_sensitive_uncertainty_for_specialists(monkeypatch):
    from app import main
    from app.routes import cases
    from fastapi.testclient import TestClient
    stored = {}
    monkeypatch.setattr(cases, 'save_profile', lambda profile: stored.update({profile.id: profile}))
    monkeypatch.setattr(cases, 'get_profile', lambda key: stored.get(key))
    async def start(key):
        return stored[key]
    monkeypatch.setattr(cases, '_ensure_eligibility_started', start)
    result = TestClient(main.app).post('/api/intake', json={'answers': complete_current_intake()})
    assert result.status_code == 200, result.text
    answers = result.json()['answers']
    assert answers['caregiver.work_authorized'] == "I'm not sure"
    assert answers['caregiver.tax_residency'] == 'Prefer not to answer'
    assert answers['recipient.lpr_since'] == "I'm not sure"
    assert answers['recipient.five_year_us_residence'] == 'Prefer not to answer'
