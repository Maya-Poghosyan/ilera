"""Reported household examples for the current intake contract."""
from app.intake.logic import QUESTIONS, answer_context, clean_answers, validate_answers, visible

PAID = 'Get paid for caregiving'
MEDICAL = 'Find health coverage'
TAX = 'Get financial support or tax savings'


def shown(field, answers):
    return visible(QUESTIONS[field].get('show_when'), answer_context(answers))


def member(kind, relationship, **patch):
    value = {"kind": kind, "relationship": relationship,
             "age": 75 if kind == "recipient" else 45,
             "lives_with_recipient": True, "tax_link": "Neither",
             "employment_status": "Retired", "income_sources": ["No income"],
             "gross_monthly_income": 0, "income_other": "", "income_varies": "No"}
    value.update(patch)
    return value


def household_answers(*, recipient=None, caregiver=None, spouse=None, others=()):
    members = [member("recipient", "Self", **(recipient or {}))]
    if spouse is not None:
        members.append(member("spouse", "Spouse or partner", **spouse))
    members.append(member("caregiver", "Child", **(caregiver or {})))
    members.extend(others)
    return {"caregiver.relationship": "Parent", "recipient.marital_status": "Yes" if spouse is not None else "No",
            "household.members": members}


def complete_current_intake():
    values = {
        'caregiver.first_name': 'Alex', 'caregiver.last_name': 'Caregiver',
        'caregiver.date_of_birth': '1980-01-01', 'caregiver.us_citizen': False,
        'caregiver.coresidence': 'Yes', 'caregiver.relationship': 'Parent',
        'caregiver.citizenship_residency': 'Another immigration status',
        'caregiver.work_authorized': "I'm not sure", 'caregiver.tax_residency': 'Prefer not to answer',
        'caregiver.employment_status': 'Retired',
        'recipient.first_name': 'Sam', 'recipient.last_name': 'Recipient',
        'recipient.date_of_birth': '1950-01-01', 'recipient.us_citizen': False,
        'recipient.citizenship_residency': 'Lawful permanent resident',
        'recipient.lpr_since': "I'm not sure", 'recipient.five_year_us_residence': 'Prefer not to answer',
        'recipient.medicare_insured_work': 'No', 'recipient.medicaid_covered': False,
        'recipient.coverage_and_benefits': ['No health coverage'],
        'recipient.marital_status': 'No', 'case.has_applied_or_received': 'No',
        'case.goals': [PAID, MEDICAL, TAX], 'tax.year': 2025,
    }
    def member(kind, relationship):
        return {'kind': kind, 'relationship': relationship, 'age': 75 if kind == 'recipient' else 45,
                'lives_with_recipient': True, 'tax_link': "I'm not sure", 'employment_status': 'Retired',
                'gross_monthly_income': "I'm not sure", 'income_sources': ["I'm not sure"],
                'income_other': '', 'income_varies': "I'm not sure"}
    values['household.members'] = [member('recipient', 'Self'), member('caregiver', 'Child')]
    for _ in range(10):
        added = False
        for question in QUESTIONS.values():
            field, kind = question['field_id'], question['type']
            if field in values or not question['required'] or not shown(field, values):
                continue
            options = question.get('options', [])
            if question.get('allow_not_sure') or "I'm not sure" in options:
                value = ["I'm not sure"] if kind in {'multi_select', 'tag_input'} else "I'm not sure"
            elif kind == 'boolean': value = False
            elif kind == 'state_dropdown': value = 'CA'
            elif kind == 'zip': value = '94601'
            elif kind in {'short_text', 'long_text'}: value = 'Test'
            elif kind == 'date': value = '2025-01-01'
            elif kind == 'number': value = question.get('validation', {}).get('min', 0)
            elif kind == 'single_select': value = options[0]
            elif kind in {'multi_select', 'tag_input'}: value = [options[0]]
            else: raise AssertionError(f'Missing realistic fixture for {field}')
            values[field] = value
            added = True
        if not added: break
    return validate_answers(clean_answers(values), complete=True)
