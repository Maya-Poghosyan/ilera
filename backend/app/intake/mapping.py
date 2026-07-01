"""Map structured intake answers (keyed by field_id) onto the existing CaseProfile.

The screening form stores every answer verbatim in ``CaseProfile.answers`` (the
canonical structured record). This module additionally projects the answers onto
the legacy ``CareRecipient`` / ``Caregiver`` / ``Household`` fields so the existing
routing + specialist agents keep working unchanged.
"""

from __future__ import annotations

from typing import Any

from ..models import CaseProfile

# Representative midpoints for the income range buckets (monthly USD).
_INCOME_MIDPOINTS: dict[str, float] = {
    "No income": 0.0,
    "Less than $1,000": 750.0,
    "$1,000–$1,499": 1250.0,
    "$1,500–$1,999": 1750.0,
    "$2,000–$2,999": 2500.0,
    "$3,000–$4,999": 4000.0,
    "$5,000 or more": 6000.0,
}

_ASSET_MIDPOINTS: dict[str, float] = {
    "Less than $2,000": 1000.0,
    "$2,000–$4,999": 3500.0,
    "$5,000–$19,999": 12500.0,
    "$20,000–$99,999": 60000.0,
    "$100,000 or more": 120000.0,
}

# Representative weekly hours for the care-hours buckets.
_HOURS_MIDPOINTS: dict[str, int] = {
    "Less than 5 hours": 3,
    "5–9 hours": 7,
    "10–19 hours": 15,
    "20–39 hours": 30,
    "40–79 hours": 60,
    "80 or more hours": 90,
    "Care is needed around the clock": 168,
}

_VA_COVERAGE = {"VA health care", "TRICARE"}
_VA_BENEFITS = {
    "VA disability compensation",
    "VA pension, Aid and Attendance, or Housebound benefits",
}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _int(value: Any) -> int | None:
    try:
        if value in (None, "", "Prefer not to answer", "I'm not sure"):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _derive_insurance(coverage: list[str], medicaid_status: str | None) -> str:
    cov = set(coverage)
    if "Medicaid" in cov or "Both Medicare and Medicaid" in cov or medicaid_status == "Enrolled now":
        return "medi-cal"
    if cov & {"Medicare Part A or Part B", "Medicare Advantage"}:
        return "medicare"
    if cov & {"Employer or union health insurance", "Marketplace or individual insurance"}:
        return "private"
    if "No health coverage" in cov:
        return "none"
    return "unknown"


def _derive_skipped_answers(answers: dict[str, Any]) -> None:
    """Auto-fill answers that can be derived from earlier base-screen responses.

    The simplified intake collects fewer fields than specialist agents expect.
    This function bridges the gap by deriving values from what was collected.
    """
    a = answers

    # The simplified form is always from a caregiver's perspective.
    if "case.user_role" not in a:
        a["case.user_role"] = "I provide care for someone else"

    # When caregiver and recipient live together, share location.
    if a.get("caregiver.coresidence") == "Yes":
        if "recipient.address.state" not in a and "caregiver.address.state" in a:
            a["recipient.address.state"] = a["caregiver.address.state"]
        if "recipient.address.zip" not in a and "caregiver.address.zip" in a:
            a["recipient.address.zip"] = a["caregiver.address.zip"]

    # Module B — caregiver.age_18_or_older from caregiver.age
    if "caregiver.age_18_or_older" not in a:
        age = _int(a.get("caregiver.age"))
        if age is not None:
            a["caregiver.age_18_or_older"] = age >= 18

    # Module B — caregiver.va_relationship_or_coresidence from relationship + coresidence
    if "caregiver.va_relationship_or_coresidence" not in a:
        rel = a.get("caregiver.relationship", "")
        cores = a.get("caregiver.coresidence", "")
        family_types = {
            "Spouse or domestic partner", "Parent", "Adult child",
            "Child under 18", "Sibling", "Grandparent", "Grandchild",
            "Other relative",
        }
        if rel and cores:
            if rel in family_types:
                a["caregiver.va_relationship_or_coresidence"] = "Family member"
            elif cores in ("Yes", "Yes, full time"):
                a["caregiver.va_relationship_or_coresidence"] = "Live together full time"
            else:
                a["caregiver.va_relationship_or_coresidence"] = "None of these"

    # Module B — recipient.va_health_enrolled from health_coverage
    if "recipient.va_health_enrolled" not in a:
        coverage = _as_list(a.get("recipient.health_coverage"))
        if "VA health care" in coverage:
            a["recipient.va_health_enrolled"] = "Yes"

    # Module C — recipient.dd_onset_before_18 from recipient.onset_age
    if "recipient.dd_onset_before_18" not in a:
        onset = a.get("recipient.onset_age")
        if onset == "Before age 18":
            a["recipient.dd_onset_before_18"] = "Yes"
        elif onset and onset not in ("I'm not sure", "There is no disability or long-term condition"):
            a["recipient.dd_onset_before_18"] = "No"

    # Module C — recipient.child_institutional_level_risk from safe_without_support
    if "recipient.child_institutional_level_risk" not in a:
        safe = a.get("recipient.safe_without_support")
        if safe == "No, they would likely need hospital, nursing-home, or other facility care":
            a["recipient.child_institutional_level_risk"] = "Yes"
        elif safe == "They are already in a facility":
            a["recipient.child_institutional_level_risk"] = "Yes"
        elif safe in ("Yes", "Maybe, but there would be significant difficulty or risk"):
            a["recipient.child_institutional_level_risk"] = "No"

    # Module D — recipient.facility_type from recipient.living_setting
    if "recipient.facility_type" not in a:
        setting = a.get("recipient.living_setting")
        if setting in ("Hospital", "Rehabilitation facility", "Nursing home or skilled nursing facility"):
            a["recipient.facility_type"] = setting

    # Module D — recipient.wants_community_transition from community_goal
    if "recipient.wants_community_transition" not in a:
        goal = a.get("recipient.community_goal")
        if goal in ("Move from a hospital or facility back into the community",
                     "Avoid moving into a nursing home or facility"):
            a["recipient.wants_community_transition"] = "Yes"


def map_answers_to_profile(answers: dict[str, Any], profile: CaseProfile) -> CaseProfile:
    """Project ``answers`` onto the legacy structured CaseProfile fields in place."""
    _derive_skipped_answers(answers)
    profile.answers = dict(answers)
    a = answers

    cr = profile.care_recipient
    cg = profile.caregiver
    hh = profile.household

    # --- care recipient personal info ----------------------------------------
    first = a.get("recipient.legal_first_name", "")
    last = a.get("recipient.legal_last_name", "")
    full_name = f"{first} {last}".strip()
    if full_name:
        cr.name = full_name
    elif a.get("recipient.preferred_name"):
        cr.name = str(a["recipient.preferred_name"])

    dob = a.get("recipient.date_of_birth")
    if dob:
        cr.date_of_birth = str(dob)

    gender = a.get("recipient.gender")
    if gender and gender != "Prefer not to answer":
        cr.gender = str(gender).lower()

    phone = a.get("recipient.phone")
    if phone:
        cr.phone = str(phone)

    email = a.get("recipient.email")
    if email:
        cr.email = str(email)

    street = a.get("recipient.address.street")
    if street:
        cr.street_address = str(street)

    city = a.get("recipient.address.city")
    if city:
        cr.city = str(city)

    zip_code = a.get("recipient.address.zip")
    if zip_code:
        cr.zip_code = str(zip_code)

    # --- care recipient medical/eligibility -----------------------------------
    age = _int(a.get("recipient.age"))
    if age is not None:
        cr.age = age

    state = a.get("recipient.address.state")
    if state:
        cr.state = str(state)

    conditions = _as_list(a.get("recipient.condition_categories"))
    if conditions:
        cr.conditions = conditions

    coverage = _as_list(a.get("recipient.health_coverage"))
    military_status = a.get("recipient.military_status")
    cr.veteran = bool(
        military_status == "Veteran"
        or set(coverage) & _VA_COVERAGE
        or set(_as_list(a.get("recipient.current_benefits"))) & _VA_BENEFITS
    )

    cr.insurance = _derive_insurance(coverage, a.get("recipient.medicaid_status"))

    current_benefits = _as_list(a.get("recipient.current_benefits"))
    if current_benefits:
        cr.current_benefits = current_benefits

    care_needs: list[str] = []
    for fid in ("recipient.adl_needs", "recipient.iadl_needs",
                "recipient.health_related_tasks", "caregiver.assistance_tasks"):
        for item in _as_list(a.get(fid)):
            if item not in {"None of these", "No", "I'm not sure"} and item not in care_needs:
                care_needs.append(item)
    if care_needs:
        cr.care_needs = care_needs

    # --- caregiver ----------------------------------------------------------
    cg_first = a.get("caregiver.legal_first_name", "")
    cg_last = a.get("caregiver.legal_last_name", "")
    cg_full = f"{cg_first} {cg_last}".strip()
    if cg_full:
        cg.name = cg_full
    elif a.get("caregiver.preferred_name"):
        cg.name = str(a["caregiver.preferred_name"])

    cg_phone = a.get("caregiver.phone")
    if cg_phone:
        cg.phone = str(cg_phone)

    cg_email = a.get("caregiver.email")
    if cg_email:
        cg.email = str(cg_email)

    cg_address = a.get("caregiver.address")
    if cg_address:
        cg.address = str(cg_address)

    relationship = a.get("caregiver.relationship")
    if relationship:
        cg.relationship = str(relationship)

    employment = _as_list(a.get("caregiver.employment_status"))
    if employment:
        cg.employment_status = ", ".join(employment)

    cg.hours_per_week = _HOURS_MIDPOINTS.get(str(a.get("caregiver.hours_weekly")))

    # --- household ----------------------------------------------------------
    hsize = _int(a.get("recipient.household_size"))
    if hsize is not None:
        hh.size = hsize

    income_range = a.get("recipient.monthly_income_range")
    if income_range in _INCOME_MIDPOINTS:
        hh.income_monthly = _INCOME_MIDPOINTS[income_range]

    asset_range = a.get("recipient.countable_assets_range")
    if asset_range in _ASSET_MIDPOINTS:
        hh.assets = _ASSET_MIDPOINTS[asset_range]

    # --- goals --------------------------------------------------------------
    goals = _as_list(a.get("case.goals"))
    if goals:
        profile.goals = goals

    return profile
