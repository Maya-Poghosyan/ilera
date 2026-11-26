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

# Optional document assistance (docs/research/document-uploads-2026-11-15/report.md). Shown after
# the section's title card; `upload_when` on a question shows it again on that question's page.
DOCUMENT_UPLOAD = {
    'max_bytes': 10 * 1024 * 1024,
    'max_pdf_pages': 12,
    'accept': ['application/pdf', 'image/jpeg', 'image/png'],
}
# Each section's one document list: what it fills, where to get it, what to cover first.
UPLOAD_DOCUMENTS = {
    'work_caregiving': [
        {'document': 'A recent paystub', 'fills': 'Pay and CASDI (SDI) deductions',
         'location': 'your payroll portal'},
        {'document': 'Dependent Care FSA plan guide or enrollment', 'fills': 'Whether you have or use a Dependent Care FSA',
         'location': 'your benefits or HR portal'},
        {'document': 'EDD Paid Family Leave notice', 'fills': 'Paid Family Leave in the past 12 months',
         'location': 'your myEDD account'},
        {'document': 'IHSS provider pay stub', 'fills': 'Whether you are paid to provide care',
         'location': 'your IHSS Electronic Services Portal account'},
    ],
    'household_assets': [
        {'document': 'A recent paystub for anyone in the household', 'fills': 'Monthly income',
         'location': 'your household’s payroll records'},
        {'document': 'Social Security or pension benefit letter', 'fills': 'Monthly benefit and SSDI start date',
         'location': 'your Social Security or pension records'},
    ],
    'tax_information': [
        {'document': 'Form 1040, pages 1–2', 'fills': 'Tax year, filing status and adjusted gross income',
         'location': 'your tax software, preparer or saved records'},
        {'document': 'W-2s', 'fills': 'Box 10 dependent care benefits',
         'location': 'your payroll portal or tax records', 'cover': 'the SSN in box a'},
        {'document': 'Form 2441, if you filed one', 'fills': 'Care costs paid and employer care benefits',
         'location': 'your filed return', 'cover': 'provider SSNs or EINs in Part I'},
    ],
    'coverage_benefits': [
        {'document': 'Medi-Cal notice', 'fills': 'Whether Medi-Cal is active',
         'location': 'your BenefitsCal account or county mail'},
        {'document': 'IHSS notice of action', 'fills': 'Whether they have applied for or receive IHSS',
         'location': 'your county IHSS mail'},
        {'document': 'Medicare card or coverage record', 'fills': 'Active Medicare parts and start dates',
         'location': 'your Medicare records or Medicare.gov account', 'cover': 'the Medicare number'},
        {'document': 'VA benefit summary letter', 'fills': 'Disability rating, pension and VA health care',
         'location': 'your letters on VA.gov'},
        {'document': 'DD-214, for a veteran', 'fills': 'Service dates and character of discharge',
         'location': 'your military records or the National Archives (eVetRecs)', 'cover': 'the SSN in block 3'},
    ],
}
for _screen in SCREENS:
    if _screen['id'] in UPLOAD_DOCUMENTS:
        _screen['upload_documents'] = UPLOAD_DOCUMENTS[_screen['id']]


def build_schema() -> dict:
    return deepcopy({"version": "2026-10-28-work-household-tax", "welcome": WELCOME,
        "submit_button": SUBMIT_BUTTON, "name_field": "recipient.first_name",
        "name_fallback": "the person you care for", "form_wide_rules": FORM_WIDE_RULES,
        "delayed_questions": DELAYED_QUESTIONS, "document_upload": DOCUMENT_UPLOAD, "screens": SCREENS})

INTAKE_SCHEMA = build_schema()
