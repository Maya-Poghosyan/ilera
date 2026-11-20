"""Topic-based intake with explicit page groups and conditional screening details."""
import json
from copy import deepcopy
from pathlib import Path

# The intake questions, section by section (authored content, edited as JSON).
SCREENS = json.loads((Path(__file__).resolve().parents[2] / "data" / "intake" / "screens.json").read_text())

WELCOME = {'header': "Let's find support that may fit your caregiving situation.", 'body': '', 'button': 'Get started'}

SUBMIT_BUTTON = 'Find possible programs'

FORM_WIDE_RULES = ['Every eligibility question should include "I\'m not sure" and "Prefer not to answer" when appropriate.',
 'Never treat "I\'m not sure" as "No."',
 'Show no more than 3–5 questions on one screen.',
 'Explain why sensitive financial or health questions are being asked.',
 'Save answers as structured fields. Do not save only a transcript.',
 'Do not ask for Social Security numbers, bank account numbers, medical record numbers, tax ID numbers, '
 'immigration document numbers, or full medical records during initial screening.',
 'Ask exact income, asset, tax, and medical details only after a specialist agent identifies a potentially '
 'relevant program.']

DELAYED_QUESTIONS = ['Social Security number',
 'Full legal name',
 'Exact bank balances',
 'Bank or routing numbers',
 'Exact tax return figures',
 'Immigration document numbers',
 'Full diagnosis list or ICD codes',
 'Medication list',
 'Physician contact information',
 'VA file number',
 'Medicaid member number',
 'Medicare number',
 'Employer tax ID',
 "Care provider's Social Security number",
 'Copies of medical records',
 'Signatures',
 'Direct-deposit information',
 'Portal usernames or passwords']

TAX_ENTRY_FIELD = 'tax.entry_method'
TAX_SKIP = 'Skip tax savings for now'


def _add_tax_entry_choice(screens: list[dict]) -> None:
    """Let caregivers use documents, answer manually, or defer the tax questions.

    Skipping hides only the Tax Information questions; household members, income,
    relationships and assets are asked in other sections and are kept."""
    tax = next(s for s in screens if s['id'] == 'tax_information')
    if tax['questions'][0]['field_id'] == TAX_ENTRY_FIELD:
        return
    not_skipped = {'not': {'field': TAX_ENTRY_FIELD, 'op': 'equals', 'value': TAX_SKIP}}
    for question in tax['questions']:
        question['show_when'] = ({'all': [not_skipped, question['show_when']]}
                                 if question.get('show_when') else not_skipped)
    tax['questions'].insert(0, {
        'field_id': TAX_ENTRY_FIELD,
        'text': 'How would you like to answer the tax questions?',
        'type': 'single_select',
        'required': True,
        'options': ['Use my documents', 'Enter answers myself', TAX_SKIP],
        'helper_text': 'Documents can suggest answers that you review. If you skip, we keep your household, '
                       'income and asset answers, and you can check tax savings later.',
        'page_group': 'Tax entry',
        'page_title': '',
        'group': 'Tax entry',
    })


_add_tax_entry_choice(SCREENS)

# Optional document assistance (docs/research/document-uploads-2026-11-15/report.md). Shown after
# the section's title card; `upload_when` on a question shows it again on that question's page.
DOCUMENT_UPLOAD = {
    'max_bytes': 10 * 1024 * 1024,
    'max_pdf_pages': 12,
    'accept': ['application/pdf', 'image/jpeg', 'image/png'],
}
UPLOAD_DOCUMENTS = {
    'work_caregiving': [
        {'document': 'A recent paystub', 'note': 'Shows CASDI (SDI) deductions and pay period'},
        {'document': 'Employer dependent-care plan guide or enrollment confirmation'},
    ],
    'household_assets': [
        {'document': 'A recent paystub for anyone in the household'},
        {'document': 'A current Social Security or pension benefit letter'},
    ],
    'tax_information': [
        {'document': 'Selected pages of a filed Form 1040', 'note': 'Pages with filing status and adjusted gross income'},
        {'document': 'W-2s', 'note': 'Box 10 shows dependent care benefits'},
        {'document': 'Form 2441, if you filed one'},
    ],
    'coverage_benefits': [
        {'document': 'A current Medi-Cal or IHSS notice'},
        {'document': 'Their Medicare card or coverage record', 'note': 'Cover the Medicare number before uploading'},
        {'document': "A short VA benefit summary letter, if they're a veteran"},
    ],
}
for _screen in SCREENS:
    if _screen['id'] in UPLOAD_DOCUMENTS:
        _screen['upload_documents'] = UPLOAD_DOCUMENTS[_screen['id']]
next(q for s in SCREENS for q in s['questions'] if q['field_id'] == TAX_ENTRY_FIELD)['upload_when'] = {
    'field': TAX_ENTRY_FIELD, 'op': 'equals', 'value': 'Use my documents'}


def build_schema() -> dict:
    return deepcopy({"version": "2026-10-28-work-household-tax", "welcome": WELCOME,
        "submit_button": SUBMIT_BUTTON, "name_field": "recipient.first_name",
        "name_fallback": "the person you care for", "form_wide_rules": FORM_WIDE_RULES,
        "delayed_questions": DELAYED_QUESTIONS, "document_upload": DOCUMENT_UPLOAD, "screens": SCREENS})

INTAKE_SCHEMA = build_schema()
