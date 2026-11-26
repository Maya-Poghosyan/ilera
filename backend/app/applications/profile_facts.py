"""Personal details an application's forms read from the shared case profile.

- Each form field with a `profile_path` reads one of these facts at fill time
- Step 1 of an application shows every fact its forms use, prefilled from the profile and editable
- Saving a fact writes the intake answer it is projected from, so intake, eligibility and every
  other application see the same value
"""

from typing import Any

from app.applications.state import AppQuestion
from app.cases.models import CaseProfile
from app.forms.schema_store import load_schema
from app.intake.documents.fields import QUESTIONS
from app.intake.logic import answer_context
from app.intake.mapping import map_answers_to_profile

RECIPIENT_GROUP = "profile.recipient"
CAREGIVER_GROUP = "profile.caregiver"
GROUP_PROMPTS = {
    RECIPIENT_GROUP: "The person you care for",
    CAREGIVER_GROUP: "You, the caregiver",
}

# Fact id (the intake answer id, or a caregiver contact attribute) -> group and on-screen label.
FACTS: dict[str, tuple[str, str]] = {
    "recipient.first_name": (RECIPIENT_GROUP, "First name"),
    "recipient.last_name": (RECIPIENT_GROUP, "Last name"),
    "recipient.date_of_birth": (RECIPIENT_GROUP, "Date of birth"),
    "recipient.address.street": (RECIPIENT_GROUP, "Street address"),
    "recipient.address.city": (RECIPIENT_GROUP, "City"),
    "recipient.address.state": (RECIPIENT_GROUP, "State"),
    "recipient.address.zip": (RECIPIENT_GROUP, "ZIP code"),
    "caregiver.first_name": (CAREGIVER_GROUP, "First name"),
    "caregiver.last_name": (CAREGIVER_GROUP, "Last name"),
    "caregiver.date_of_birth": (CAREGIVER_GROUP, "Date of birth"),
    "caregiver.relationship": (CAREGIVER_GROUP, "The person you care for is your…"),
    "caregiver.phone": (CAREGIVER_GROUP, "Phone number"),
    "caregiver.email": (CAREGIVER_GROUP, "Email address"),
    "caregiver.address.street": (CAREGIVER_GROUP, "Street address"),
    "caregiver.address.city": (CAREGIVER_GROUP, "City"),
    "caregiver.address.state": (CAREGIVER_GROUP, "State"),
    "caregiver.address.zip": (CAREGIVER_GROUP, "ZIP code"),
}

# Contact details kept on the caregiver directly (from the account), not as intake answers.
CONTACT = {"caregiver.phone": "phone", "caregiver.email": "email"}
OPTIONAL = set(CONTACT)

_ADDRESS = {"street_address": "street", "city": "city", "state": "state", "zip_code": "zip"}
_NAME = ("first_name", "last_name")


def _facts_for_path(path: str) -> list[str]:
    """The facts a form's `profile_path` is built from; empty for ones edited elsewhere."""
    root, _, name = path.partition(".")
    subject = {"care_recipient": "recipient", "caregiver": "caregiver"}.get(root)
    if subject is None:
        return []
    if name == "name":
        return [f"{subject}.{part}" for part in _NAME]
    if name in _ADDRESS:
        return [f"{subject}.address.{_ADDRESS[name]}"]
    if subject == "caregiver" and name == "address":
        return [f"caregiver.address.{part}" for part in _ADDRESS.values()]
    fact = f"{subject}.{name}"
    return [fact] if fact in FACTS else []


def program_facts(form_ids: list[str], profile: CaseProfile) -> list[str]:
    """Facts the program's forms use, in screen order.

    - A recipient who lives with the caregiver shares the caregiver's address, so it is asked once
    """
    used = {fact for form_id in form_ids
            for spec in (load_schema(form_id).get("fields") or {}).values()
            for fact in _facts_for_path(spec.get("profile_path") or "")}
    if profile.answers.get("caregiver.coresidence") == "Yes":
        used = {f.replace("recipient.address.", "caregiver.address.", 1) for f in used}
    return [fact for fact in FACTS if fact in used]


def _profile_attribute(profile: CaseProfile, fact: str) -> Any:
    """The typed profile value a fact is projected onto, e.g. caregiver.address.zip -> caregiver.zip_code."""
    subject, _, name = fact.partition(".")
    branch = profile.care_recipient if subject == "recipient" else profile.caregiver
    if name.startswith("address."):
        part = name.removeprefix("address.")
        name = next(attr for attr, p in _ADDRESS.items() if p == part)
    return getattr(branch, name, None)


def fact_value(profile: CaseProfile, fact: str) -> Any:
    """The fact's current value: the intake answer, else the typed profile value (e.g. from the account)."""
    if fact in CONTACT:
        return getattr(profile.caregiver, CONTACT[fact]) or None
    value = answer_context(profile.answers).get(fact)
    if value in ("", None):
        value = _profile_attribute(profile, fact)
    return None if value in ("", None) else value


def fact_questions(facts: list[str]) -> list[AppQuestion]:
    questions = []
    for fact in facts:
        group, label = FACTS[fact]
        intake = QUESTIONS.get(fact, {})
        questions.append(AppQuestion(
            field_id=fact,
            text=label,
            type=intake.get("type", "short_text"),
            required=fact not in OPTIONAL,
            options=[] if intake.get("type") == "state_dropdown" else list(intake.get("options") or []),
            group_id=group,
            group_prompt=GROUP_PROMPTS[group],
            input=fact,
        ))
    return questions


def is_fact(field_id: str) -> bool:
    return field_id in FACTS


def apply_facts(profile: CaseProfile, values: dict[str, Any]) -> CaseProfile:
    """Write edited facts into the profile through the intake projection."""
    intake = {fact: value for fact, value in values.items() if fact not in CONTACT}
    if intake:
        map_answers_to_profile(intake, profile)
    for fact, attribute in CONTACT.items():
        if fact in values:
            setattr(profile.caregiver, attribute, str(values[fact] or "").strip())
    return profile
