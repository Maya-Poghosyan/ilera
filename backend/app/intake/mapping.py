"""Map structured intake answers (keyed by field_id) onto the existing CaseProfile.

The screening form stores every answer verbatim in ``CaseProfile.answers`` (the
canonical structured record). This module additionally projects the answers onto
the legacy ``CareRecipient`` / ``Caregiver`` / ``Household`` fields so the existing
routing + specialist agents keep working unchanged.
"""

from __future__ import annotations

from typing import Any

from ..geo import normalize_county, zip_to_county
from ..models import CaseProfile

# Representative midpoints for the income range buckets (monthly USD).
_INCOME_MIDPOINTS: dict[str, float] = {
    "No income": 0.0,
    "Less than $1,000": 750.0,
    "$1,000–$1,999": 1500.0,
    "$2,000–$2,999": 2500.0,
    "$3,000–$4,999": 4000.0,
    "$5,000 or more": 6000.0,
}

_VA_COVERAGE = {"VA health care", "TRICARE"}
_VA_BENEFITS = {
    "VA disability compensation",
    "VA pension, Aid and Attendance, or Housebound benefits",
    "VA pension or Aid and Attendance",
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
    if cov & {"Medicare Part A or Part B", "Medicare Advantage", "Medicare"}:
        return "medicare"
    if cov & {"Employer or union health insurance", "Marketplace or individual insurance", "Employer or private insurance"}:
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
        for part in ("street", "city", "state", "county", "zip"):
            mine, theirs = f"caregiver.address.{part}", f"recipient.address.{part}"
            if theirs not in a and mine in a:
                a[theirs] = a[mine]

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
    # Forms want the parts, prose wants the whole, so both are kept.
    cr.first_name = str(a.get("recipient.first_name") or cr.first_name)
    cr.last_name = str(a.get("recipient.last_name") or cr.last_name)
    if cr.first_name or cr.last_name:
        cr.name = f"{cr.first_name} {cr.last_name}".strip()

    dob = a.get("recipient.date_of_birth")
    if dob:
        cr.date_of_birth = str(dob)

    zip_code = a.get("recipient.address.zip")
    if zip_code:
        cr.zip_code = str(zip_code)

    # --- care recipient medical/eligibility -----------------------------------
    # Derive age from date_of_birth when available
    age = _int(a.get("recipient.age"))
    if age is None and dob:
        from datetime import date as _date
        try:
            bd = _date.fromisoformat(str(dob))
            today = _date.today()
            age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            a["recipient.age"] = age  # store so mini-module triggers can use it
        except (ValueError, TypeError):
            pass
    if age is not None:
        cr.age = age

    state = a.get("recipient.address.state")
    if state:
        cr.state = str(state)

    street = a.get("recipient.address.street")
    if street:
        cr.street_address = str(street)

    city = a.get("recipient.address.city")
    if city:
        cr.city = str(city)

    # Many programs are county-administered. Prefer what the user told us; a ZIP can
    # straddle a county line, so the lookup is only a fallback.
    county = a.get("recipient.address.county") or zip_to_county(cr.zip_code, cr.state)
    if county:
        cr.county = normalize_county(county)

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
    for item in _as_list(a.get("recipient.adl_needs")):
        if item not in {"None of these", "No", "I'm not sure"} and item not in care_needs:
            care_needs.append(item)
    if care_needs:
        cr.care_needs = care_needs

    # --- caregiver ----------------------------------------------------------
    cg.first_name = str(a.get("caregiver.first_name") or cg.first_name)
    cg.last_name = str(a.get("caregiver.last_name") or cg.last_name)
    if cg.first_name or cg.last_name:
        cg.name = f"{cg.first_name} {cg.last_name}".strip()

    cg_phone = a.get("caregiver.phone")
    if cg_phone:
        cg.phone = str(cg_phone)

    cg_email = a.get("caregiver.email")
    if cg_email:
        cg.email = str(cg_email)

    cg.street_address = str(a.get("caregiver.address.street") or cg.street_address)
    cg.city = str(a.get("caregiver.address.city") or cg.city)
    cg.state = str(a.get("caregiver.address.state") or cg.state)
    cg.zip_code = str(a.get("caregiver.address.zip") or cg.zip_code)
    if a.get("caregiver.address.county"):
        cg.county = normalize_county(str(a["caregiver.address.county"]))
    if cg.state or cg.zip_code:
        cg.address = f"{cg.state} {cg.zip_code}".strip()

    relationship = a.get("caregiver.relationship")
    if relationship:
        cg.relationship = str(relationship)

    employment = a.get("caregiver.employment_status")
    if employment:
        cg.employment_status = str(employment)

    # --- household ----------------------------------------------------------
    hsize = _int(a.get("recipient.household_size"))
    if hsize is not None:
        hh.size = hsize

    income_range = a.get("recipient.monthly_income_range")
    if income_range in _INCOME_MIDPOINTS:
        hh.income_monthly = _INCOME_MIDPOINTS[income_range]

    return profile
