"""Ilera benefits intake — schema-driven question set.

The entire intake (Welcome, Screens 1–9 / Q1–Q42, and Conditional Mini-Modules
A–F) is encoded here as *data*, not hardcoded JSX. The frontend fetches this via
``GET /api/intake/schema`` and renders + drives conditional logic from it.

Each question carries:
  - ``field_id``      exact id from the spec (e.g. ``recipient.adl_needs``)
  - ``screen``        which screen / mini-module it belongs to
  - ``text``          the question text (``[recipient name]`` is interpolated client-side)
  - ``type``          single_select | multi_select | number | short_text |
                      long_text | state_dropdown | zip | date | boolean
  - ``options``       literal option labels (for select types)
  - ``required``      bool
  - ``helper_text`` / ``why_this_matters`` where the spec provides them
  - ``show_when``     machine-readable condition referencing other field_ids
  - ``validation``    e.g. exclusive options
  - ``allow_not_sure`` / ``allow_prefer_not_to_answer`` for non-select types

``show_when`` grammar (all conditions reference previously-answered field_ids)::

    leaf  = {"field": <field_id>, "op": <op>, "value": <value>}
    group = {"any": [cond, ...]} | {"all": [cond, ...]} | {"not": cond}
    ops   = equals | not_equals | in | includes | includes_any |
            gte | lte | gt | lt | answered | blank
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# condition helpers (build machine-readable show_when trees)
# ---------------------------------------------------------------------------


def eq(field: str, value: Any) -> dict:
    return {"field": field, "op": "equals", "value": value}


def in_(field: str, values: list) -> dict:
    return {"field": field, "op": "in", "value": values}


def includes_any(field: str, values: list) -> dict:
    return {"field": field, "op": "includes_any", "value": values}


def gte(field: str, value: Any) -> dict:
    return {"field": field, "op": "gte", "value": value}


def lt(field: str, value: Any) -> dict:
    return {"field": field, "op": "lt", "value": value}


def any_(*conds: dict) -> dict:
    return {"any": list(conds)}


def all_(*conds: dict) -> dict:
    return {"all": list(conds)}


def not_(cond: dict) -> dict:
    return {"not": cond}


# Reusable condition: the user is acting as a caregiver (drives Screen-6/8 gating).
IS_CAREGIVER = in_(
    "case.user_role",
    [
        "I provide care for someone else",
        "I both receive care and provide care",
    ],
)

CAREGIVER_EMPLOYED = includes_any(
    "caregiver.employment_status",
    [
        "Employed full time",
        "Employed part time",
        "Self-employed",
        "Gig or contract work",
    ],
)

# Q11 option groups reused across show_when / triggers.
Q11_DISABILITY_OR_LONGTERM = [
    "Physical disability or mobility limitation",
    "Blindness or significant vision loss",
    "Intellectual or developmental disability",
    "Autism",
    "Memory loss, Alzheimer's disease, or another form of dementia",
    "Serious or chronic medical condition",
    "Injury",
    "Work-related injury or occupational illness",
]
Q21_MEDICARE = [
    "Medicare Part A or Part B",
    "Medicare Advantage",
    "Both Medicare and Medicaid",
]
Q23_VA_BENEFITS = [
    "VA disability compensation",
    "VA pension, Aid and Attendance, or Housebound benefits",
]


def q(
    field_id: str,
    text: str,
    type: str,
    required: bool,
    *,
    options: list[str] | None = None,
    helper_text: str | None = None,
    why_this_matters: str | None = None,
    show_when: dict | None = None,
    validation: dict | None = None,
    allow_not_sure: bool = False,
    allow_prefer_not_to_answer: bool = False,
    alt_ui: str | None = None,
    system_behavior: str | None = None,
    group: str | None = None,
    layout: str | None = None,
) -> dict:
    out: dict[str, Any] = {
        "field_id": field_id,
        "text": text,
        "type": type,
        "required": required,
    }
    if options is not None:
        out["options"] = options
    if helper_text:
        out["helper_text"] = helper_text
    if why_this_matters:
        out["why_this_matters"] = why_this_matters
    if show_when is not None:
        out["show_when"] = show_when
    if validation is not None:
        out["validation"] = validation
    if allow_not_sure:
        out["allow_not_sure"] = True
    if allow_prefer_not_to_answer:
        out["allow_prefer_not_to_answer"] = True
    if alt_ui:
        out["alt_ui"] = alt_ui
    if system_behavior:
        out["system_behavior"] = system_behavior
    if group:
        out["group"] = group
    if layout:
        out["layout"] = layout
    return out


# ---------------------------------------------------------------------------
# Screens 1–9 (Q1–Q42)
# ---------------------------------------------------------------------------

CONDITION_SUGGESTIONS: list[str] = [
    "Physical disability or mobility limitation",
    "Blindness or significant vision loss",
    "Intellectual or developmental disability",
    "Autism",
    "Memory loss, Alzheimer's disease, or another form of dementia",
    "Serious or chronic medical condition",
    "Mental health condition",
    "Terminal illness",
    "Injury",
    "Work-related injury or occupational illness",
    "Recovery after surgery or hospitalization",
    "Age-related frailty",
]


SCREENS: list[dict] = [
    # ---- Section 1: Who Are We Helping ------------------------------------
    {
        "id": "screen_1",
        "title": "Who are we helping?",
        "questions": [
            q(
                "caregiver.preferred_name",
                "What is your name?",
                "short_text",
                True,
                helper_text="A first name or nickname is fine.",
                group="caregiver_info",
            ),
            q(
                "caregiver.address.state",
                "State",
                "state_dropdown",
                True,
                group="caregiver_info",
                layout="inline",
            ),
            q(
                "caregiver.address.zip",
                "ZIP code",
                "zip",
                True,
                group="caregiver_info",
                layout="inline",
            ),
            q(
                "recipient.preferred_name",
                "What is the name of the person you care for?",
                "short_text",
                True,
                helper_text="A first name or nickname is fine.",
                group="recipient_info",
            ),
            q(
                "recipient.age",
                "How old are they?",
                "number",
                True,
                group="recipient_info",
            ),
            q(
                "caregiver.coresidence",
                "Do they live with you?",
                "single_select",
                True,
                options=["Yes", "No"],
                group="recipient_info",
            ),
            q(
                "recipient.address.state",
                "[recipient name]'s state",
                "state_dropdown",
                True,
                show_when=eq("caregiver.coresidence", "No"),
                group="recipient_location",
                layout="inline",
            ),
            q(
                "recipient.address.zip",
                "[recipient name]'s ZIP code",
                "zip",
                True,
                show_when=eq("caregiver.coresidence", "No"),
                group="recipient_location",
                layout="inline",
            ),
        ],
    },
    # ---- Section 2: Care Situation ----------------------------------------
    {
        "id": "screen_2",
        "title": "Care situation",
        "questions": [
            q(
                "caregiver.relationship",
                "What is your relationship to [recipient name]?",
                "single_select",
                True,
                options=[
                    "Spouse or domestic partner",
                    "Parent",
                    "Adult child",
                    "Child under 18",
                    "Sibling",
                    "Grandparent",
                    "Grandchild",
                    "Other relative",
                    "Friend, neighbor, or other unpaid caregiver",
                    "Legal guardian or authorized representative",
                    "Paid caregiver",
                    "Other",
                ],
            ),
            q(
                "recipient.condition_categories",
                "What conditions or care needs does [recipient name] have?",
                "tag_input",
                True,
                options=CONDITION_SUGGESTIONS,
                helper_text="Type to search or add your own.",
                group="conditions",
            ),
            q(
                "recipient.condition_documented",
                "Have these been documented by a medical professional?",
                "single_select",
                True,
                options=["Yes", "No", "I'm not sure"],
                group="conditions",
            ),
            q(
                "recipient.adl_needs",
                "What help does [recipient name] need?",
                "multi_select",
                True,
                options=[
                    "Bathing or showering",
                    "Dressing",
                    "Grooming or personal hygiene",
                    "Using the toilet",
                    "Eating or drinking",
                    "Moving around or transfers",
                    "Medication management",
                    "Supervision for safety",
                    "None of these",
                    "I'm not sure",
                ],
                validation={"exclusive_options": ["None of these"]},
            ),
            q(
                "caregiver.assistance_tasks",
                "What tasks do you assist with?",
                "multi_select",
                True,
                options=[
                    "Personal care (bathing, dressing, toileting)",
                    "Meal preparation",
                    "Medication management",
                    "Transportation or driving",
                    "Housekeeping or laundry",
                    "Shopping or errands",
                    "Managing finances or paperwork",
                    "Scheduling appointments",
                    "Emotional support or companionship",
                    "Supervision or safety monitoring",
                    "Medical tasks (wound care, injections, etc.)",
                    "Other",
                ],
            ),
            q(
                "recipient.other_care_sources",
                "Is anyone else helping you care for [recipient name]?",
                "multi_select",
                True,
                options=[
                    "Other family members or friends",
                    "Home-care or personal-care agency",
                    "Home health nurses or therapists",
                    "Adult day services",
                    "Facility staff",
                    "No one else",
                    "Other",
                ],
                validation={"exclusive_options": ["No one else"]},
            ),
            q(
                "caregiver.impact",
                "How has caregiving impacted your life?",
                "multi_select",
                True,
                options=[
                    "Reduced work hours or left a job",
                    "Financial strain",
                    "Less time for myself or my family",
                    "Physical health effects",
                    "Emotional stress, anxiety, or burnout",
                    "Social isolation",
                    "Difficulty maintaining relationships",
                    "Housing instability or changes",
                    "Had to relocate",
                    "None of the above",
                ],
                validation={"exclusive_options": ["None of the above"]},
            ),
        ],
    },
    # ---- Section 3: Financials & Coverage ---------------------------------
    {
        "id": "screen_3",
        "title": "Financials & Coverage",
        "questions": [
            q(
                "recipient.household_size",
                "How many people live in the household?",
                "number",
                True,
                helper_text="Include [recipient name].",
            ),
            q(
                "recipient.monthly_income_range",
                "What is the approximate monthly household income?",
                "single_select",
                True,
                options=[
                    "No income",
                    "Less than $1,000",
                    "$1,000\u2013$1,999",
                    "$2,000\u2013$2,999",
                    "$3,000\u2013$4,999",
                    "$5,000 or more",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.medicaid_status",
                "What is [recipient name]'s Medicaid status?",
                "single_select",
                True,
                options=[
                    "Enrolled now",
                    "Application pending",
                    "Previously denied",
                    "Has not applied",
                    "I'm not sure",
                ],
                helper_text="Medicaid may have a different name in your state, such as Medi-Cal in California.",
            ),
            q(
                "recipient.current_benefits",
                "Does [recipient name] currently receive any of these?",
                "multi_select",
                True,
                options=[
                    "SSI",
                    "SSDI or Social Security Disability",
                    "Social Security retirement or survivor benefits",
                    "Medicaid home- and community-based services",
                    "VA disability compensation",
                    "VA pension or Aid and Attendance",
                    "SNAP or food assistance",
                    "Housing assistance",
                    "Workers' compensation",
                    "None of these",
                    "Other",
                    "I'm not sure",
                ],
                validation={"exclusive_options": ["None of these"]},
            ),
        ],
    },
]

CONTACT_SCREEN: dict = {
    "id": "screen_contact",
    "title": "Contact",
    "questions": [
        q(
            "caregiver.phone",
            "What is your phone number?",
            "short_text",
            True,
        ),
        q(
            "caregiver.email",
            "What is your email address?",
            "short_text",
            True,
        ),
    ],
}


# ---------------------------------------------------------------------------
# Conditional Mini-Modules A–F
# ---------------------------------------------------------------------------

MINI_MODULES: list[dict] = [
    {
        "id": "module_a",
        "title": "Employment and leave",
        "trigger": any_(
            includes_any(
                "caregiver.employment_status",
                [
                    "Employed full time",
                    "Employed part time",
                    "Self-employed",
                    "Gig or contract work",
                    "Not working because of caregiving",
                ],
            ),
            includes_any(
                "caregiver.leave_goals",
                [
                    "Paid family or medical leave",
                    "Unpaid job-protected leave",
                    "Using paid sick leave to provide care",
                    "A flexible or reduced work schedule",
                ],
            ),
        ),
        "routing": [
            "Federal FMLA Agent",
            "State Paid Leave Agent",
            "State Sick Leave/Kin Care Agent",
            "Employer Benefits Agent",
        ],
        "questions": [
            q("caregiver.work_state", "In what state do you work?", "state_dropdown", True),
            q(
                "caregiver.employer_type",
                "What kind of employer do you work for?",
                "single_select",
                True,
                options=[
                    "Private company or nonprofit",
                    "Federal government",
                    "State or local government",
                    "School",
                    "Household or individual employer",
                    "Self-employed",
                    "Gig or contract platform",
                    "I'm not sure",
                ],
            ),
            q(
                "caregiver.employer_tenure",
                "How long have you worked for this employer?",
                "single_select",
                True,
                options=[
                    "Less than 6 months",
                    "6–11 months",
                    "At least 12 months",
                    "Work has been seasonal or has included breaks",
                    "I'm not sure",
                ],
            ),
            q(
                "caregiver.hours_worked_last_12_months",
                "About how many hours have you worked for this employer during the last 12 months?",
                "single_select",
                True,
                options=[
                    "Less than 1,250 hours",
                    "At least 1,250 hours",
                    "I have not worked there for 12 months",
                    "I'm not sure",
                ],
            ),
            q(
                "caregiver.employer_size_75_miles",
                "About how many employees work for your employer within 75 miles of your worksite?",
                "single_select",
                True,
                options=[
                    "Fewer than 50",
                    "50 or more",
                    "I work remotely and do not know which worksite applies",
                    "I'm not sure",
                ],
            ),
            q(
                "caregiver.leave_relationship",
                "Who do you need leave to care for?",
                "single_select",
                True,
                options=[
                    "The person named earlier in this form",
                    "A different person",
                ],
                system_behavior="Use the relationship already captured in Q3 and ask only if the leave is for a different person.",
            ),
            q(
                "caregiver.leave_pattern",
                "What kind of time away from work do you expect to need?",
                "single_select",
                True,
                options=[
                    "One continuous period",
                    "Separate days or hours as needed",
                    "A reduced weekly schedule",
                    "I already took leave",
                    "I'm not sure",
                ],
            ),
            q(
                "caregiver.leave_start",
                "When do you expect the leave to begin?",
                "date",
                False,
                allow_not_sure=True,
            ),
        ],
    },
    {
        "id": "module_b",
        "title": "Veteran or military care",
        "trigger": any_(
            includes_any("recipient.health_coverage", ["VA health care", "TRICARE"]),
            includes_any("recipient.current_benefits", Q23_VA_BENEFITS),
            includes_any("case.goals", ["Finding VA caregiver benefits"]),
        ),
        "routing": [
            "VA PCAFC Agent",
            "VA PGCSS Agent",
            "VA Aid and Attendance/Housebound Agent",
            "Veteran Directed Care Agent",
            "CHAMPVA Agent",
            "Military Caregiver Leave Agent",
        ],
        "questions": [
            q(
                "recipient.military_status",
                "Which statement describes [recipient name]?",
                "single_select",
                True,
                options=[
                    "Veteran",
                    "Current active-duty service member",
                    "National Guard or Reserve member",
                    "Surviving spouse of a veteran",
                    "Dependent of a veteran",
                    "None of these",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.va_rating",
                "Does [recipient name] have a VA service-connected disability rating?",
                "single_select",
                True,
                options=[
                    "No rating",
                    "Less than 70%",
                    "70% or higher",
                    "Rating decision is pending",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.military_discharge_status",
                "Was [recipient name] discharged from the military, or do they have a date of medical discharge?",
                "single_select",
                True,
                options=[
                    "Yes",
                    "Medical discharge is scheduled",
                    "No",
                    "Not applicable",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.va_six_month_care_need",
                "Is [recipient name] expected to need continuous, in-person personal care for at least 6 months?",
                "single_select",
                True,
                options=["Yes", "No", "I'm not sure"],
            ),
            q(
                "caregiver.age_18_or_older",
                "Are you at least 18 years old?",
                "boolean",
                True,
                show_when=any_(
                    {"field": "caregiver.age", "op": "blank"},
                    lt("caregiver.age", 18),
                ),
                system_behavior="Derive from Q4 (caregiver.age) when possible; do not ask twice.",
            ),
            q(
                "recipient.va_pension_status",
                "Does [recipient name] currently receive a VA pension, Aid and Attendance, or Housebound benefits?",
                "single_select",
                True,
                options=[
                    "VA pension only",
                    "Aid and Attendance",
                    "Housebound",
                    "Application pending",
                    "No",
                    "I'm not sure",
                ],
            ),
        ],
    },
    {
        "id": "module_c",
        "title": "Child or developmental disability",
        "trigger": any_(
            lt("recipient.age", 22),
            includes_any(
                "recipient.condition_categories",
                ["Autism", "Intellectual or developmental disability"],
            ),
            eq("recipient.onset_age", "Before age 18"),
        ),
        "routing": [
            "Katie Beckett/TEFRA Agent",
            "Children's Medicaid/HCBS Agent",
            "SSI Child Agent",
            "Developmental Disability/Regional Center Agent",
            "Respite and Disease-Specific Grant Agent",
        ],
        "questions": [
            q(
                "recipient.lives_with_parent",
                "Does [recipient name] live with one or both parents?",
                "single_select",
                True,
                options=["Yes", "No", "Part of the time", "I'm not sure"],
            ),
            q(
                "recipient.medicaid_denied_parent_income",
                "Has [recipient name] been denied Medicaid because the household or parents' income was too high?",
                "single_select",
                True,
                options=[
                    "Yes",
                    "No",
                    "Application pending",
                    "Has not applied",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.dd_onset_before_18",
                "Did the developmental disability begin before age 18?",
                "single_select",
                True,
                options=["Yes", "No", "I'm not sure"],
                show_when={"field": "recipient.onset_age", "op": "blank"},
            ),
            q(
                "recipient.child_disability_services",
                "Is [recipient name] currently receiving special education, early intervention, or developmental-disability services?",
                "multi_select",
                True,
                options=[
                    "Early intervention",
                    "IEP or special education",
                    "State developmental-disability agency or Regional Center",
                    "Medicaid waiver",
                    "None",
                    "I'm not sure",
                ],
            ),
        ],
    },
    {
        "id": "module_d",
        "title": "Facility transition",
        "trigger": any_(
            in_(
                "recipient.living_setting",
                [
                    "Hospital",
                    "Rehabilitation facility",
                    "Nursing home or skilled nursing facility",
                    "Group home",
                    "Assisted living or a licensed residential care setting",
                ],
            ),
            eq("recipient.community_goal", "Move from a hospital or facility back into the community"),
        ),
        "routing": [
            "Money Follows the Person/Transition Agent",
            "Medicaid HCBS Agent",
            "PACE Agent",
            "Housing and Home Modification Agent",
        ],
        "questions": [
            q(
                "recipient.facility_length_of_stay",
                "About how long has [recipient name] been there?",
                "single_select",
                True,
                options=[
                    "Less than 30 days",
                    "30–89 days",
                    "90 days–5 months",
                    "6 months or longer",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.community_destination_available",
                "Is there a home or community setting available for [recipient name] to move to?",
                "single_select",
                True,
                options=[
                    "Yes",
                    "Not yet, but we are looking",
                    "No",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.transition_support",
                "Is a discharge planner, social worker, or transition coordinator already involved?",
                "single_select",
                True,
                options=["Yes", "No", "I'm not sure"],
            ),
        ],
    },
    {
        "id": "module_e",
        "title": "Tax and out-of-pocket costs",
        "trigger": any_(
            includes_any(
                "case.goals",
                [
                    "Tax credits, deductions, or dependent-care benefits",
                    "Saving money without affecting benefits",
                ],
            ),
            CAREGIVER_EMPLOYED,
            eq(
                "caregiver.payment_status",
                "Yes, through Medicaid, a waiver, IHSS, or another public program",
            ),
        ),
        "routing": [
            "Dependent/Other Dependent Credit Agent",
            "Child and Dependent Care Credit Agent",
            "Medical Expense Deduction Agent",
            "Dependent Care FSA Agent",
            "IRS Notice 2014-7 Agent",
            "State Caregiver Tax Credit Agent",
        ],
        "questions": [
            q(
                "tax.provides_over_half_support",
                "Do you provide more than half of [recipient name]'s total financial support?",
                "single_select",
                True,
                options=["Yes", "No", "About half", "I'm not sure"],
            ),
            q(
                "tax.lived_together_over_half_year",
                "Did [recipient name] live with you for more than half of the tax year?",
                "single_select",
                True,
                options=["Yes", "No", "The year is not over yet", "I'm not sure"],
            ),
            q(
                "tax.paid_care_to_work",
                "Did you pay someone to care for [recipient name] so you or your spouse could work, look for work, or attend school?",
                "single_select",
                True,
                options=["Yes", "No", "I'm not sure"],
            ),
            q(
                "tax.unreimbursed_medical_expenses",
                "Did you pay unreimbursed medical, dental, long-term-care, transportation, equipment, or home-modification expenses for [recipient name]?",
                "single_select",
                True,
                options=["Yes", "No", "I'm not sure"],
            ),
            q(
                "tax.dependent_care_fsa_available",
                "Does your employer offer a Dependent Care FSA or another caregiving benefit?",
                "single_select",
                True,
                options=[
                    "Yes, and I use it",
                    "Yes, but I do not use it",
                    "No",
                    "I'm not sure",
                ],
                show_when=CAREGIVER_EMPLOYED,
            ),
            q(
                "tax.waiver_payment_cophysical_residence",
                "If you are paid through a Medicaid waiver or similar program, do you live in the same home as [recipient name]?",
                "single_select",
                True,
                options=["Yes", "No", "I'm not sure"],
                show_when=eq(
                    "caregiver.payment_status",
                    "Yes, through Medicaid, a waiver, IHSS, or another public program",
                ),
            ),
        ],
    },
    {
        "id": "module_f",
        "title": "Disability income and savings",
        "trigger": any_(
            all_(
                includes_any(
                    "recipient.condition_categories",
                    [
                        "Physical disability or mobility limitation",
                        "Blindness or significant vision loss",
                        "Serious or chronic medical condition",
                        "Memory loss, Alzheimer's disease, or another form of dementia",
                        "Injury",
                        "Work-related injury or occupational illness",
                        "Intellectual or developmental disability",
                        "Autism",
                    ],
                ),
                not_(includes_any("recipient.current_benefits", ["SSI", "SSDI or Social Security Disability"])),
            ),
            includes_any(
                "case.goals",
                [
                    "Getting SSI, SSDI, or other income support for the person receiving care",
                    "Saving money without affecting benefits",
                ],
            ),
        ),
        "routing": [
            "SSI Agent",
            "SSDI Agent",
            "ABLE Account Agent",
            "Special Needs Trust Referral Agent",
        ],
        "questions": [
            q(
                "recipient.work_status",
                "Is [recipient name] currently working?",
                "single_select",
                True,
                options=[
                    "No",
                    "Yes, part time",
                    "Yes, full time",
                    "Self-employed",
                    "Work is irregular",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.condition_limits_work",
                "Does the condition prevent or substantially limit [recipient name]'s ability to work?",
                "single_select",
                True,
                options=[
                    "Yes",
                    "No",
                    "[recipient name] is a child or has not yet worked",
                    "[recipient name] is past retirement age",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.work_history_social_security",
                "Has [recipient name] worked and paid Social Security taxes in the past?",
                "single_select",
                True,
                options=[
                    "Yes, for several years",
                    "Yes, but only briefly or a long time ago",
                    "No",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.able_interest",
                "Is [recipient name] interested in saving for disability-related expenses without disrupting means-tested benefits?",
                "single_select",
                True,
                options=["Yes", "No", "I'm not sure"],
            ),
        ],
    },
]


WELCOME = {
    "header": "Let's find support that may fit your caregiving situation.",
    "body": (
        "We'll ask a few short questions about you, the person you care for, "
        "and your situation. This takes about 5 minutes."
    ),
    "button": "Get started",
}

SUBMIT_BUTTON = "Find possible programs"

FORM_WIDE_RULES = [
    'Every eligibility question should include "I\'m not sure" and "Prefer not to answer" when appropriate.',
    'Never treat "I\'m not sure" as "No."',
    "Show no more than 3–5 questions on one screen.",
    "Explain why sensitive financial or health questions are being asked.",
    "Save answers as structured fields. Do not save only a transcript.",
    "Do not ask for Social Security numbers, bank account numbers, medical record numbers, "
    "tax ID numbers, immigration document numbers, or full medical records during initial screening.",
    "Ask exact income, asset, tax, and medical details only after a specialist agent identifies "
    "a potentially relevant program.",
]

# QUESTIONS TO DELIBERATELY DELAY — these must NOT appear in the screening form.
DELAYED_QUESTIONS = [
    "Social Security number",
    "Full legal name",
    "Exact bank balances",
    "Bank or routing numbers",
    "Exact tax return figures",
    "Immigration document numbers",
    "Full diagnosis list or ICD codes",
    "Medication list",
    "Physician contact information",
    "VA file number",
    "Medicaid member number",
    "Medicare number",
    "Employer tax ID",
    "Care provider's Social Security number",
    "Copies of medical records",
    "Signatures",
    "Direct-deposit information",
    "Portal usernames or passwords",
]


def build_schema() -> dict:
    """Return the full intake schema as a JSON-serializable dict."""
    return {
        "version": "2026-06-21",
        "welcome": WELCOME,
        "submit_button": SUBMIT_BUTTON,
        "name_field": "recipient.preferred_name",
        "name_fallback": "the person you care for",
        "form_wide_rules": FORM_WIDE_RULES,
        "delayed_questions": DELAYED_QUESTIONS,
        "screens": SCREENS,
        "contact_screen": CONTACT_SCREEN,
        "mini_modules": MINI_MODULES,
    }


INTAKE_SCHEMA: dict = build_schema()
