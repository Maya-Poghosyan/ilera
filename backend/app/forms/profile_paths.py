"""The vocabulary a form map is allowed to draw on.

`form_schemas/<form_id>.json` points each PDF field at a dotted `profile_path`, which
`filler._dig` resolves against a `CaseProfile`. A path that doesn't exist resolves to
`None` and silently leaves the field blank, so both the map generator and its validator
work from this enumeration rather than from guesswork.

Only the intake-derived branches are offered. The orchestration fields (`band_*`,
`findings`, `strategy`, ...) are about running the eligibility session, never about
what goes on a government form.
"""

from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel

from ..intake import schema as intake_schema
from ..models import Caregiver, CareRecipient, Household

# Branches of CaseProfile a form field may reference, in the order they're presented.
_ROOTS: list[tuple[str, type[BaseModel]]] = [
    ("care_recipient", CareRecipient),
    ("caregiver", Caregiver),
    ("household", Household),
]

# Declared on the model but never written by intake.mapping, so they always resolve to
# the empty default. Mapping a PDF field to one of these is worse than leaving it
# unmapped: `resolve_fields` reports an empty value as `missing` rather than asking the
# user, so the field silently prints blank. SSN and the rest of these are deliberately
# withheld at screening time (see intake.schema.DELAYED_QUESTIONS); forms that need them
# must ask. `tests/test_profile_paths.py` fails if intake starts populating one.
_NOT_COLLECTED = frozenset({
    "care_recipient.gender",
    "care_recipient.phone",
    "care_recipient.email",
    "care_recipient.ssn",
    "caregiver.hours_per_week",
})


# What a path holds is not always obvious from its name, and a plausible-looking wrong
# mapping prints wrong data onto a government form.
_NOTES: dict[str, str] = {
    "care_recipient.name": (
        "first and last together, the person receiving care (the applicant on most "
        "forms) — a box wanting only one part takes `first_name`/`last_name` instead"
    ),
    "caregiver.name": (
        "first and last together, the person providing care (the provider/attendant) — "
        "a box wanting only one part takes `first_name`/`last_name` instead"
    ),
    "caregiver.address": "state and ZIP only, e.g. 'CA 90001' — NOT a street address",
    "caregiver.street_address": "number and street, no city/state/ZIP",
    "care_recipient.street_address": "number and street, no city/state/ZIP",
    "care_recipient.conditions": "free-text diagnoses/conditions the user typed",
    "care_recipient.care_needs": "activities of daily living the recipient needs help with",
    "care_recipient.insurance": (
        "the single primary coverage type, picked in priority order, NOT a list of "
        "everything held — 'medi-cal' does not mean the person lacks Medicare, so never "
        "answer a 'do you have <specific coverage>?' question from this"
    ),
}

# Paths whose value always comes from a fixed intake option list. A `check_when` or
# `value_map` key outside that list can never match, so the field silently stays blank;
# the exact strings are handed to the generator and enforced by its validator.
_VALUE_SOURCE: dict[str, str] = {
    "caregiver.relationship": "caregiver.relationship",
    "caregiver.employment_status": "caregiver.employment_status",
    "care_recipient.care_needs": "recipient.adl_needs",
    "care_recipient.current_benefits": "recipient.current_benefits",
}

# Option labels that mean "no answer"; intake.mapping strips them before they land on
# the profile, so they are never values a form field can be matched against.
_NON_ANSWERS = {"I'm not sure", "Prefer not to answer", "None of these"}


def _intake_options(field_id: str) -> list[str]:
    schema = intake_schema.build_schema()
    groups = [*schema["screens"], *schema["mini_modules"], schema["contact_screen"]]
    for group in groups:
        for question in group["questions"]:
            if question["field_id"] == field_id:
                return [o for o in question.get("options") or [] if o not in _NON_ANSWERS]
    return []


def profile_values() -> dict[str, list[str]]:
    """Paths that can only hold one of a known set of values, and that set."""
    values: dict[str, list[str]] = {}
    for prefix, model in _ROOTS:
        for name, field in model.model_fields.items():
            if get_origin(field.annotation) is Literal:
                values[f"{prefix}.{name}"] = [str(v) for v in get_args(field.annotation)]
            elif field.annotation is bool:
                values[f"{prefix}.{name}"] = ["True", "False"]
    for path, field_id in _VALUE_SOURCE.items():
        options = _intake_options(field_id)
        if options:
            values[path] = options
    return values


def _describe(annotation: Any) -> str:
    """A short, prompt-friendly rendering of a field's type."""
    origin = get_origin(annotation)
    if origin is Literal:
        return "one of: " + ", ".join(repr(v) for v in get_args(annotation))
    if origin is Union:
        inner = [a for a in get_args(annotation) if a is not type(None)]
        return " or ".join(_describe(a) for a in inner) + " (may be empty)"
    if origin is list:
        args = get_args(annotation)
        return f"list of {_describe(args[0])}" if args else "list"
    return getattr(annotation, "__name__", str(annotation))


def profile_paths() -> dict[str, str]:
    """Every legal `profile_path`, mapped to a description of its type."""
    paths: dict[str, str] = {}
    for prefix, model in _ROOTS:
        for name, field in model.model_fields.items():
            path = f"{prefix}.{name}"
            if path in _NOT_COLLECTED:
                continue
            paths[path] = _describe(field.annotation)
    return paths


def describe_profile_paths() -> str:
    """The vocabulary as a plain-text list, for inclusion in a prompt."""
    values = profile_values()
    lines: list[str] = []
    for path, kind in profile_paths().items():
        line = f"- {path} ({kind})"
        if path in _NOTES:
            line += f" — {_NOTES[path]}"
        known = values.get(path)
        if known and not kind.startswith("one of:"):
            # `_describe` already spells out Literal members; this covers the paths whose
            # value set comes from intake's option lists instead of the type.
            line += "\n    exact values: " + ", ".join(f'"{v}"' for v in known)
        lines.append(line)
    return "\n".join(lines)
