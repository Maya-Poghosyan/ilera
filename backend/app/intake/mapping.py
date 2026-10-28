"""Project current user answers into typed facts without inventing skipped answers.

Raw answers, computed context and fact evidence have separate responsibilities.
Partial patches preserve untouched answers; changed/hidden intake facts clear stale
values. Facts resolved outside intake retain their provenance and values.
"""
from typing import Any

from ..eligibility.facts import write_fact
from ..geo import normalize_county, zip_to_county
from ..models import CaseProfile
from .logic import UNKNOWN, answer_context, clean_answers

_BINDINGS = {
    **{f"care_recipient.{name}": f"recipient.{name}" for name in
       ("first_name", "last_name", "date_of_birth", "us_citizen", "living_setting", "health_coverage", "medicaid_status", "current_benefits")},
    **{f"caregiver.{name}": f"caregiver.{name}" for name in
       ("first_name", "last_name", "date_of_birth", "us_citizen", "relationship", "employment_status")},
    **{f"{root}.{name}": f"{subject}.address.{part}"
       for root, subject in (("care_recipient", "recipient"), ("caregiver", "caregiver"))
       for name, part in (("street_address", "street"), ("city", "city"), ("state", "state"), ("county", "county"), ("zip_code", "zip"))},
    "care_recipient.conditions": "recipient.condition_categories",
    "care_recipient.care_needs": "recipient.adl_needs",
    "household.size": "recipient.household_size",
    "household.income_monthly_range": "recipient.monthly_income_range",
}


def _availability(value: Any) -> str:
    values = value if isinstance(value, list) else [value]
    if "Prefer not to answer" in values:
        return "skipped"
    return "unknown" if value is None or isinstance(value, str) and not value.strip() or any(v in UNKNOWN for v in values if isinstance(v, str)) else "known"


def _write(profile: CaseProfile, path: str, value: Any, field: str, *, derived=False, precision="exact"):
    metadata = profile.fact_metadata.get(path)
    if metadata and not (metadata.source_ref or "").startswith("intake:"):
        return
    availability = _availability(value)
    if availability == "known" and isinstance(value, list):
        value = [v for v in value if v not in {"None of these", "No"}]
    write_fact(profile, path, value, availability=availability,
               source_ref=f"intake:{field}", source_kind="derived" if derived else "user_report", precision=precision)


def map_answers_to_profile(answers: dict[str, Any], profile: CaseProfile) -> CaseProfile:
    # Work on a copy: invalid typed evidence never partially mutates the caller.
    updated = profile.model_copy(deep=True)
    previous = updated.answers
    merged = {**previous, **answers}
    raw = clean_answers(merged)
    context = answer_context(raw)
    previous_context = answer_context(previous)
    affected = set(answers) | (set(previous) - set(raw))
    affected |= {key for key in previous_context.keys() | context.keys()
                 if previous_context.get(key) != context.get(key)}
    affected |= {key for key in previous.keys() & raw.keys() if previous[key] != raw[key]}
    updated.answers = raw
    if affected & {"recipient.coverage_and_benefits", "recipient.medicaid_covered"}:
        affected.update({"recipient.health_coverage", "recipient.current_benefits", "recipient.medicaid_status"})
    if affected & {"household.members", "recipient.marital_status", "caregiver.coresidence", "caregiver.relationship"}:
        affected.add("recipient.household_size")
        _write(updated,"household.reported_income_monthly",context.get("household.reported_income_monthly"),"household.members",derived=True,precision="derived")
        for root,prefix in [("care_recipient","recipient"),("caregiver","caregiver")]:
            for key in ["income_sources","gross_monthly_income"]:
                _write(updated,root+'.'+key,context.get(prefix+'.'+key),"household.members",derived=True)
        _write(updated,"care_recipient.employment_status",context.get("recipient.employment_status"),"household.members",derived=True)
    for path, field in _BINDINGS.items():
        shared = field.startswith("recipient.address.") and raw.get("caregiver.coresidence") == "Yes"
        if field not in affected and not (field.startswith("recipient.address.") and "caregiver.coresidence" in affected) and not (shared and ("caregiver.coresidence" in affected
                or field.replace("recipient.", "caregiver.", 1) in affected)):
            continue
        value = context.get(field)
        if path == "household.income_monthly_range":
            label = raw.get(field)
            _write(updated, path, label, field, precision="bucket")
            # “No income” establishes exactly zero. Other buckets do not establish
            # an exact number and must never fill a PDF with a fabricated midpoint.
            _write(updated, "household.income_monthly", 0.0 if label == "No income" else None,
                   field, derived=True)

        else:
            if path.endswith(".county") and _availability(value) == "known":
                value = normalize_county(value)
            household_derived = field == "caregiver.employment_status" and value != raw.get(field)
            source = "caregiver.coresidence" if shared else "household.members" if household_derived else field
            _write(updated, path, value, source, derived=shared or household_derived)
    for root,prefix in [("care_recipient","recipient"),("caregiver","caregiver")]:
        if prefix+".date_of_birth" in affected:
            _write(updated,root+".age",context.get(prefix+".age"),prefix+".date_of_birth",derived=True)
    for root in ("care_recipient", "caregiver"):
        if any(f"{'recipient' if root == 'care_recipient' else root}.{n}" in affected for n in ("first_name", "last_name")):
            branch = getattr(updated, root)
            _write(updated, f"{root}.name", f"{branch.first_name} {branch.last_name}".strip(),
                   f"{'recipient' if root == 'care_recipient' else root}.first_name", derived=True)
    if any(k in affected for k in ("recipient.health_coverage", "recipient.medicaid_status")):
        cov = set(updated.care_recipient.health_coverage)
        status = updated.care_recipient.medicaid_status
        insurance = ("medi-cal" if "Medicaid" in cov or "Both Medicare and Medicaid" in cov or status == "Enrolled now"
                     else "medicare" if "Medicare" in cov else "private" if "Employer or private insurance" in cov
                     else "none" if "No health coverage" in cov else None)
        _write(updated, "care_recipient.insurance", insurance, "recipient.health_coverage", derived=True)
    if "recipient.military_status" in affected:
        status = raw.get("recipient.military_status")
        _write(updated, "care_recipient.veteran", None if _availability(status) != "known" else status == "Veteran", "recipient.military_status", derived=True)
    if any(k.startswith("caregiver.address.") for k in affected):
        cg = updated.caregiver
        _write(updated, "caregiver.address", f"{cg.state} {cg.zip_code}".strip(), "caregiver.address.state", derived=True)
    # County inference is presentation context, not reported fact evidence.
    if not updated.care_recipient.county and updated.care_recipient.zip_code:
        county = zip_to_county(updated.care_recipient.zip_code, updated.care_recipient.state)
        if county:
            _write(updated, "care_recipient.county", normalize_county(county), "recipient.address.zip", derived=True)
    for name in CaseProfile.model_fields:
        setattr(profile, name, getattr(updated, name))
    return profile


def apply_account_contact(profile: CaseProfile, *, name: str = "", email: str = "", phone: str = "") -> CaseProfile:
    caregiver = profile.caregiver
    if email:
        caregiver.email = email
    if phone:
        caregiver.phone = phone
    if name and not caregiver.name:
        caregiver.name = name
        parts = name.split()
        if parts and not caregiver.first_name:
            caregiver.first_name = parts[0]
        if len(parts) > 1 and not caregiver.last_name:
            caregiver.last_name = " ".join(parts[1:])
    return profile
