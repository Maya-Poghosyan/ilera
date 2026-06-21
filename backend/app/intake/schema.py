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
    return out


# ---------------------------------------------------------------------------
# Screens 1–9 (Q1–Q42)
# ---------------------------------------------------------------------------

SCREENS: list[dict] = [
    {
        "id": "screen_1",
        "title": "Who are we helping?",
        "questions": [
            q(
                "case.user_role",
                "Who are you looking for support for?",
                "single_select",
                True,
                options=[
                    "I receive care and want support for myself",
                    "I provide care for someone else",
                    "I both receive care and provide care",
                    "I am helping someone complete this form",
                    "Other",
                ],
            ),
            q(
                "recipient.preferred_name",
                "What should we call the person who receives care?",
                "short_text",
                False,
                helper_text="A first name or nickname is enough. You do not need to enter a legal name yet.",
            ),
            q(
                "caregiver.relationship",
                "What is your relationship to [recipient name]?",
                "single_select",
                True,
                options=[
                    "I am the person receiving care",
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
                "caregiver.age",
                "How old are you?",
                "number",
                False,
                helper_text="Some caregiver programs use the caregiver's age, including programs for older relatives and certain VA benefits.",
                allow_prefer_not_to_answer=True,
            ),
            q(
                "caregiver.coresidence",
                "Do you currently live with [recipient name]?",
                "single_select",
                True,
                options=[
                    "Yes, full time",
                    "Yes, part of the time",
                    "No",
                    "No, but I would be willing to live together",
                    "We plan to live together soon",
                    "I'm not sure",
                ],
            ),
        ],
    },
    {
        "id": "screen_2",
        "title": "Location and living situation",
        "questions": [
            q(
                "recipient.address.state",
                "What state does [recipient name] live in?",
                "state_dropdown",
                True,
            ),
            q(
                "recipient.address.zip",
                "What is [recipient name]'s ZIP code?",
                "zip",
                True,
                helper_text="Many caregiver programs are run by the state, county, or a local service area.",
                system_behavior="Derive county from ZIP when possible. Ask the user to confirm only when a ZIP crosses county boundaries.",
            ),
            q(
                "recipient.living_setting",
                "Where does [recipient name] live now?",
                "single_select",
                True,
                options=[
                    "Their own house or apartment",
                    "A family member's or friend's home",
                    "Assisted living or a licensed residential care setting",
                    "Nursing home or skilled nursing facility",
                    "Hospital",
                    "Rehabilitation facility",
                    "Group home",
                    "Temporary housing or no stable housing",
                    "Other",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.community_goal",
                "Which statement best describes the current goal?",
                "single_select",
                True,
                options=[
                    "Remain safely at home",
                    "Move from a hospital or facility back into the community",
                    "Avoid moving into a nursing home or facility",
                    "Find a safer residential setting",
                    "No move is currently being considered",
                    "I'm not sure",
                ],
            ),
        ],
    },
    {
        "id": "screen_3",
        "title": "About the person receiving care",
        "questions": [
            q(
                "recipient.age",
                "How old is [recipient name]?",
                "number",
                True,
                alt_ui="Allow 'Enter date of birth instead,' but do not require a full date of birth during screening.",
            ),
            q(
                "recipient.condition_categories",
                "Which of the following describe why [recipient name] needs care?",
                "multi_select",
                True,
                options=[
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
                    "They do not have a diagnosis, but they need help",
                    "Other",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.condition_documented",
                "Has a licensed health care professional diagnosed or documented the condition or care need?",
                "single_select",
                True,
                options=[
                    "Yes",
                    "No",
                    "An evaluation is scheduled or in progress",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.expected_duration",
                "About how long is the condition or care need expected to last?",
                "single_select",
                True,
                options=[
                    "Less than 3 months",
                    "3 to 5 months",
                    "6 to 11 months",
                    "At least 12 months",
                    "Permanent or expected to continue indefinitely",
                    "It changes or comes and goes",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.onset_age",
                "At what age did the disability or long-term condition begin?",
                "single_select",
                False,
                options=[
                    "Before age 18",
                    "Ages 18–25",
                    "Ages 26–45",
                    "Age 46 or later",
                    "There is no disability or long-term condition",
                    "I'm not sure",
                ],
                show_when=includes_any("recipient.condition_categories", Q11_DISABILITY_OR_LONGTERM),
                why_this_matters="This routes developmental-disability programs, disability benefits, and ABLE-account screening. Beginning in 2026, ABLE eligibility generally looks at whether disability began before age 46.",
            ),
        ],
    },
    {
        "id": "screen_4",
        "title": "Help needed day to day",
        "intro_text": "Select anything [recipient name] cannot do safely alone, needs reminders or supervision for, or needs another person to complete.",
        "questions": [
            q(
                "recipient.adl_needs",
                "Which personal care activities does [recipient name] need help with?",
                "multi_select",
                True,
                options=[
                    "Bathing or showering",
                    "Dressing",
                    "Grooming or personal hygiene",
                    "Using the toilet",
                    "Managing incontinence",
                    "Eating or drinking",
                    "Moving between a bed, chair, or wheelchair",
                    "Walking or moving around the home",
                    "Repositioning in bed",
                    "None of these",
                    "I'm not sure",
                ],
                validation={"exclusive_options": ["None of these"]},
            ),
            q(
                "recipient.iadl_needs",
                "Which household or community activities does [recipient name] need help with?",
                "multi_select",
                True,
                options=[
                    "Preparing meals",
                    "Grocery shopping",
                    "Cleaning or laundry",
                    "Managing medications",
                    "Making appointments or coordinating care",
                    "Transportation",
                    "Managing money, bills, or paperwork",
                    "Using a phone, computer, or communication device",
                    "Leaving home or navigating the community",
                    "None of these",
                    "I'm not sure",
                ],
                validation={"exclusive_options": ["None of these"]},
            ),
            q(
                "recipient.supervision_need",
                "Does [recipient name] need another person nearby for safety, reminders, protection, or decision-making?",
                "single_select",
                True,
                options=[
                    "No",
                    "Occasionally",
                    "Every day for part of the day",
                    "Most of the day",
                    "At all times or cannot safely be left alone",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.health_related_tasks",
                "Does [recipient name] need help with medical or nursing-related tasks at home?",
                "multi_select",
                True,
                options=[
                    "Medication setup, reminders, or administration",
                    "Injections",
                    "Wound care",
                    "Catheter, ostomy, feeding tube, or similar care",
                    "Monitoring symptoms or vital signs",
                    "Therapy exercises prescribed by a professional",
                    "Medical equipment",
                    "Other health-related task",
                    "No",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.unpaid_care_hours_weekly",
                "About how many hours of help does [recipient name] receive from all unpaid caregivers in a typical week?",
                "single_select",
                True,
                options=[
                    "Less than 5 hours",
                    "5–9 hours",
                    "10–19 hours",
                    "20–39 hours",
                    "40–79 hours",
                    "80 or more hours",
                    "Care is needed around the clock",
                    "The amount changes a lot",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.safe_without_support",
                "Without this help, could [recipient name] remain safely in a home or community setting?",
                "single_select",
                True,
                options=[
                    "Yes",
                    "Maybe, but there would be significant difficulty or risk",
                    "No, they would likely need hospital, nursing-home, or other facility care",
                    "They are already in a facility",
                    "I'm not sure",
                ],
            ),
        ],
    },
    {
        "id": "screen_5",
        "title": "Health coverage and current support",
        "questions": [
            q(
                "recipient.health_coverage",
                "What health coverage does [recipient name] currently have?",
                "multi_select",
                True,
                options=[
                    "Medicaid",
                    "Medicare Part A or Part B",
                    "Medicare Advantage",
                    "Both Medicare and Medicaid",
                    "VA health care",
                    "Employer or union health insurance",
                    "Marketplace or individual insurance",
                    "TRICARE",
                    "No health coverage",
                    "Other",
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
                    "Previously enrolled, but coverage ended",
                    "Has not applied",
                    "I'm not sure",
                ],
                helper_text="Medicaid may have a different name in your state, such as Medi-Cal in California.",
            ),
            q(
                "recipient.current_benefits",
                "Which benefits or services does [recipient name] currently receive?",
                "multi_select",
                True,
                options=[
                    "SSI",
                    "SSDI or Social Security Disability",
                    "Social Security retirement or survivor benefits",
                    "Medicaid home- and community-based services or a waiver",
                    "State-paid in-home care, personal care, or consumer-directed services",
                    "PACE",
                    "Medicare hospice",
                    "VA disability compensation",
                    "VA pension, Aid and Attendance, or Housebound benefits",
                    "SNAP or food assistance",
                    "Housing assistance",
                    "Long-term care insurance payments",
                    "Workers' compensation or an injury settlement",
                    "Regional Center or developmental-disability services",
                    "Respite or Area Agency on Aging services",
                    "None of these",
                    "Other",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.hospice_status",
                "Is [recipient name] currently enrolled in hospice care?",
                "single_select",
                True,
                options=[
                    "Yes",
                    "No",
                    "Hospice has been discussed or an evaluation is pending",
                    "I'm not sure",
                ],
                show_when=any_(
                    includes_any(
                        "recipient.condition_categories",
                        [
                            "Terminal illness",
                            "Serious or chronic medical condition",
                            "Memory loss, Alzheimer's disease, or another form of dementia",
                            "I'm not sure",
                        ],
                    ),
                    includes_any("recipient.health_coverage", Q21_MEDICARE),
                ),
            ),
            q(
                "recipient.dementia_diagnosis",
                "Has a health care professional diagnosed [recipient name] with Alzheimer's disease or another form of dementia?",
                "single_select",
                True,
                options=[
                    "Yes",
                    "No",
                    "An evaluation is scheduled or in progress",
                    "I'm not sure",
                ],
                show_when=any_(
                    includes_any(
                        "recipient.condition_categories",
                        [
                            "Memory loss, Alzheimer's disease, or another form of dementia",
                            "Age-related frailty",
                            "Serious or chronic medical condition",
                            "I'm not sure",
                        ],
                    ),
                    gte("recipient.age", 60),
                ),
            ),
        ],
    },
    {
        "id": "screen_6",
        "title": "The caregiving arrangement",
        "questions": [
            q(
                "caregiver.role_status",
                "Which statement best describes your caregiving role?",
                "single_select",
                True,
                options=[
                    "I am the main caregiver",
                    "I share caregiving with other family members or friends",
                    "I provide backup or occasional care",
                    "I coordinate care but provide little hands-on help",
                    "I am preparing to become a caregiver",
                    "I am the person receiving care",
                    "Other",
                ],
            ),
            q(
                "caregiver.hours_weekly",
                "About how many hours of care do you personally provide in a typical week?",
                "single_select",
                True,
                options=[
                    "Less than 5 hours",
                    "5–9 hours",
                    "10–19 hours",
                    "20–39 hours",
                    "40–79 hours",
                    "80 or more hours",
                    "Care is needed around the clock",
                    "The amount changes a lot",
                    "I'm not sure",
                ],
                show_when=IS_CAREGIVER,
            ),
            q(
                "caregiver.care_duration",
                "How long have you been providing this care?",
                "single_select",
                True,
                options=[
                    "I have not started yet",
                    "Less than 3 months",
                    "3–5 months",
                    "6–11 months",
                    "1–2 years",
                    "More than 2 years",
                    "I'm not sure",
                ],
                show_when=IS_CAREGIVER,
            ),
            q(
                "caregiver.payment_status",
                "Are you currently paid for any of the care you provide?",
                "single_select",
                True,
                options=[
                    "No, I am unpaid",
                    "Yes, through Medicaid, a waiver, IHSS, or another public program",
                    "Yes, by [recipient name] or their family",
                    "Yes, through a home-care agency",
                    "Yes, through long-term care insurance",
                    "Yes, from another source",
                    "Payment has been approved but has not started",
                    "I'm not sure",
                ],
                show_when=IS_CAREGIVER,
            ),
            q(
                "recipient.other_care_sources",
                "Does [recipient name] also receive care from anyone else?",
                "multi_select",
                True,
                options=[
                    "Other unpaid family members or friends",
                    "A paid family caregiver",
                    "A home-care or personal-care agency",
                    "Home health nurses or therapists",
                    "Adult day services",
                    "Facility staff",
                    "No one else",
                    "Other",
                    "I'm not sure",
                ],
            ),
        ],
    },
    {
        "id": "screen_7",
        "title": "Financial snapshot",
        "intro_text": "These ranges help identify programs worth exploring. They are not a final Medicaid, SSI, or tax calculation. Do not include the caregiver's income unless the question specifically asks for it.",
        "questions": [
            q(
                "recipient.marital_status",
                "Is [recipient name] married?",
                "single_select",
                True,
                options=[
                    "No",
                    "Yes, living with spouse",
                    "Yes, living apart from spouse",
                    "Widowed",
                    "Divorced or legally separated",
                    "I'm not sure",
                    "Prefer not to answer",
                ],
            ),
            q(
                "recipient.household_size",
                "How many people live in [recipient name]'s household, including [recipient name]?",
                "number",
                True,
            ),
            q(
                "recipient.monthly_income_range",
                "About how much total income does [recipient name] receive each month before taxes?",
                "single_select",
                True,
                options=[
                    "No income",
                    "Less than $1,000",
                    "$1,000–$1,499",
                    "$1,500–$1,999",
                    "$2,000–$2,999",
                    "$3,000–$4,999",
                    "$5,000 or more",
                    "Income changes month to month",
                    "I'm not sure",
                    "Prefer not to answer",
                ],
                helper_text="Include wages, Social Security, pensions, disability payments, and regular cash income. A specialist may later ask for the exact amount and whether a spouse's or parent's income must be counted.",
            ),
            q(
                "recipient.income_sources",
                "What kinds of income does [recipient name] receive?",
                "multi_select",
                True,
                options=[
                    "Wages or self-employment",
                    "SSI",
                    "SSDI",
                    "Social Security retirement or survivor benefits",
                    "Pension or retirement withdrawals",
                    "VA disability compensation",
                    "VA pension",
                    "Workers' compensation",
                    "Unemployment benefits",
                    "Child support or alimony",
                    "Investment or rental income",
                    "Regular financial help from family or others",
                    "No income",
                    "Other",
                    "I'm not sure",
                ],
            ),
            q(
                "recipient.countable_assets_range",
                "About how much does [recipient name] have in cash, checking, savings, and investments?",
                "single_select",
                True,
                options=[
                    "Less than $2,000",
                    "$2,000–$4,999",
                    "$5,000–$19,999",
                    "$20,000–$99,999",
                    "$100,000 or more",
                    "I'm not sure",
                    "Prefer not to answer",
                ],
                helper_text="For this estimate, do not count the home they live in, one everyday vehicle, or ordinary personal belongings. Program rules differ, and a specialist will confirm what counts.",
            ),
            q(
                "recipient.special_assets",
                "Is [recipient name] expecting or holding any of the following?",
                "multi_select",
                False,
                options=[
                    "Inheritance",
                    "Personal-injury or workers' compensation settlement",
                    "Trust",
                    "Special needs trust",
                    "ABLE account",
                    "Life-insurance cash value",
                    "Property other than the home they live in",
                    "None of these",
                    "I'm not sure",
                    "Prefer not to answer",
                ],
            ),
        ],
    },
    {
        "id": "screen_8",
        "title": "Work and leave",
        "questions": [
            q(
                "caregiver.employment_status",
                "What is your current work situation?",
                "multi_select",
                True,
                options=[
                    "Employed full time",
                    "Employed part time",
                    "Self-employed",
                    "Gig or contract work",
                    "Unemployed and looking for work",
                    "Not working because of caregiving",
                    "Student",
                    "Retired",
                    "Not currently working for another reason",
                    "Prefer not to answer",
                ],
                show_when=IS_CAREGIVER,
            ),
            q(
                "caregiver.work_impact",
                "Has caregiving affected your work or school?",
                "multi_select",
                True,
                options=[
                    "I have missed work or school",
                    "I reduced my hours",
                    "I took unpaid leave",
                    "I used paid time off or sick leave",
                    "I left a job or school program",
                    "I turned down work",
                    "I expect to need time off soon",
                    "It has not affected work or school",
                    "Other",
                    "Prefer not to answer",
                ],
                show_when=IS_CAREGIVER,
            ),
            q(
                "caregiver.leave_goals",
                "Would any of these help you?",
                "multi_select",
                True,
                options=[
                    "Paid family or medical leave",
                    "Unpaid job-protected leave",
                    "Using paid sick leave to provide care",
                    "A flexible or reduced work schedule",
                    "Help understanding employer benefits",
                    "Help returning to work",
                    "None of these",
                    "I'm not sure",
                ],
                show_when=includes_any(
                    "caregiver.employment_status",
                    [
                        "Employed full time",
                        "Employed part time",
                        "Self-employed",
                        "Gig or contract work",
                        "Unemployed and looking for work",
                        "Not working because of caregiving",
                        "Student",
                    ],
                ),
            ),
        ],
    },
    {
        "id": "screen_9",
        "title": "What help are you looking for?",
        "questions": [
            q(
                "case.goals",
                "What would you most like help with?",
                "multi_select",
                True,
                options=[
                    "Getting paid as a family or friend caregiver",
                    "Finding in-home personal care",
                    "Getting a break from caregiving or respite care",
                    "Getting paid leave or job protection",
                    "Applying for Medicaid",
                    "Finding Medicare caregiver or dementia support",
                    "Finding VA caregiver benefits",
                    "Getting SSI, SSDI, or other income support for the person receiving care",
                    "Meals, transportation, adult day care, or household help",
                    "Home or vehicle modifications",
                    "Moving home from a hospital or facility",
                    "Tax credits, deductions, or dependent-care benefits",
                    "Saving money without affecting benefits",
                    "Finding grants from nonprofit or disease-specific organizations",
                    "Completing or submitting applications",
                    "Renewing current benefits",
                    "I'm not sure where to start",
                    "Other",
                ],
            ),
            q(
                "case.urgency",
                "Is there a deadline or urgent change we should know about?",
                "multi_select",
                False,
                options=[
                    "Hospital or facility discharge is coming up",
                    "Current benefits may end soon",
                    "A benefits renewal is due",
                    "I need leave from work soon",
                    "The current caregiver arrangement may break down",
                    "Housing is unstable",
                    "Care needs recently increased",
                    "There is no immediate deadline",
                    "Other",
                ],
            ),
            q(
                "case.additional_context",
                "Is there anything else you want the eligibility agents to know?",
                "long_text",
                False,
                helper_text="Do not enter Social Security numbers, bank information, passwords, or full medical records.",
            ),
        ],
    },
    {
        "id": "screen_10",
        "title": "Contact and personal information",
        "intro_text": "We need a few details to pre-fill your benefit applications. This saves you from typing the same information into every form.",
        "questions": [
            q(
                "recipient.legal_first_name",
                "What is [recipient name]'s legal first name?",
                "short_text",
                True,
            ),
            q(
                "recipient.legal_last_name",
                "What is [recipient name]'s legal last name?",
                "short_text",
                True,
            ),
            q(
                "recipient.date_of_birth",
                "What is [recipient name]'s date of birth?",
                "date",
                True,
            ),
            q(
                "recipient.gender",
                "What is [recipient name]'s gender?",
                "single_select",
                False,
                options=["Male", "Female", "Non-binary", "Prefer not to answer"],
                allow_prefer_not_to_answer=True,
            ),
            q(
                "recipient.phone",
                "What is [recipient name]'s phone number?",
                "short_text",
                False,
            ),
            q(
                "recipient.email",
                "What is [recipient name]'s email address?",
                "short_text",
                False,
            ),
            q(
                "recipient.address.street",
                "What is [recipient name]'s street address?",
                "short_text",
                True,
            ),
            q(
                "recipient.address.city",
                "City",
                "short_text",
                True,
            ),
            q(
                "caregiver.legal_first_name",
                "What is the caregiver's legal first name?",
                "short_text",
                True,
                show_when=IS_CAREGIVER,
            ),
            q(
                "caregiver.legal_last_name",
                "What is the caregiver's legal last name?",
                "short_text",
                True,
                show_when=IS_CAREGIVER,
            ),
            q(
                "caregiver.phone",
                "What is the caregiver's phone number?",
                "short_text",
                False,
                show_when=IS_CAREGIVER,
            ),
            q(
                "caregiver.address",
                "What is the caregiver's home address?",
                "short_text",
                False,
                show_when=IS_CAREGIVER,
                helper_text="Only needed if different from the care recipient's address.",
            ),
        ],
    },
]


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
                "recipient.va_health_enrolled",
                "Is [recipient name] enrolled in VA health care?",
                "single_select",
                True,
                options=["Yes", "Application pending", "No", "I'm not sure"],
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
                system_behavior="Derive from Q4 (caregiver.age) when possible; do not ask twice.",
            ),
            q(
                "caregiver.va_relationship_or_coresidence",
                "Are you a family member of the veteran, or do you live with or plan to live full time with the veteran?",
                "single_select",
                True,
                options=[
                    "Family member",
                    "Live together full time",
                    "Willing to live together full time",
                    "None of these",
                    "I'm not sure",
                ],
                system_behavior="Derive from Q3 (caregiver.relationship) and Q5 (caregiver.coresidence) when possible; ask only if unresolved.",
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
                "recipient.child_institutional_level_risk",
                "Would [recipient name] likely need hospital, nursing-facility, or institutional care without services at home?",
                "single_select",
                True,
                options=["Yes", "No", "I'm not sure"],
            ),
            q(
                "recipient.dd_onset_before_18",
                "Did the developmental disability begin before age 18?",
                "single_select",
                True,
                options=["Yes", "No", "I'm not sure"],
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
                "recipient.facility_type",
                "What type of facility is [recipient name] in?",
                "single_select",
                True,
                options=[
                    "Hospital",
                    "Rehabilitation facility",
                    "Nursing home or skilled nursing facility",
                    "Intermediate care facility",
                    "Psychiatric facility",
                    "Other",
                    "I'm not sure",
                ],
            ),
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
                "recipient.wants_community_transition",
                "Does [recipient name] want to return to a home or community setting?",
                "single_select",
                True,
                options=[
                    "Yes",
                    "No",
                    "Maybe",
                    "They cannot express a preference",
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
        "We will start with a short set of questions about the person receiving care, "
        "the help they need, and your caregiving situation. You can choose \"I'm not sure\" "
        "whenever you do not know an answer. Based on your answers, we may ask a few "
        "additional questions for programs that appear relevant."
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
        "mini_modules": MINI_MODULES,
    }


INTAKE_SCHEMA: dict = build_schema()
