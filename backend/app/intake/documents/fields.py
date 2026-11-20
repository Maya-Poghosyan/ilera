"""Which intake facts a document may suggest, and how model output becomes a valid answer.

`SPECS` is the single place to add or change a suggestible field: the model's output schema,
its prompt and the validation below are all derived from it and from the intake schema."""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.intake.schema import SCREENS
from app.intake.documents.models import AnswerSuggestion, IncomeSuggestion, Source

QUESTIONS = {q["field_id"]: q for s in SCREENS for q in s["questions"]}

CAREGIVER = frozenset({"caregiver"})
FILERS = frozenset({"caregiver", "spouse"})
RECIPIENT = frozenset({"recipient"})


def _past_tax_year(raw: str) -> int:
    year = int(raw)
    if not 2000 <= year <= date.today().year:
        raise ValueError
    return year


def _va_rating(raw: str) -> str:
    pct = int(raw.rstrip("%"))
    if not 0 <= pct <= 100 or pct % 10:
        raise ValueError
    return "70% or higher" if pct >= 70 else "Less than 70%"


@dataclass(frozen=True)
class FieldSpec:
    people: frozenset[str]           # whose fact it may be; anything else is dropped
    hint: str                        # what the model should look for
    values: tuple[str, ...] = ()     # allowed subset of the question's options
    parse: Callable[[str], Any] | None = None  # overrides the question-type default
    needs_tax_year: bool = False     # the fact belongs to one filed year


SPECS: dict[str, FieldSpec] = {
    "caregiver.sdi_deductions": FieldSpec(
        CAREGIVER, "only when a paystub shows a CASDI, CA SDI or SDI deduction", values=("Yes",)),
    "tax.dependent_care_fsa_available": FieldSpec(
        CAREGIVER, '"Yes, and I use it" for an enrollment confirmation or paid claim; '
        '"Yes, but I do not use it" for a plan guide or offer only; "No" only when stated',
        values=("Yes, and I use it", "Yes, but I do not use it", "No")),
    "tax.year": FieldSpec(FILERS, "the 4-digit tax year of a filed return, W-2 or Form 2441", parse=_past_tax_year),
    "tax.adjusted_gross_income": FieldSpec(
        FILERS, "adjusted gross income on a filed Form 1040, as a plain number", needs_tax_year=True),
    "tax.filing_status": FieldSpec(
        FILERS, "only the status checked on a filed Form 1040", needs_tax_year=True,
        values=("Single", "Married filing jointly", "Married filing separately", "Head of household",
                "Qualifying surviving spouse")),
    "recipient.medicaid_covered": FieldSpec(
        RECIPIENT, '"true" only when a current Medi-Cal notice says coverage is approved or active'),
    "recipient.medicare_parts": FieldSpec(
        RECIPIENT, 'parts shown as active, separated by "; "', values=("Part A (hospital)", "Part B (medical)")),
    "recipient.medicare_part_a_start": FieldSpec(RECIPIENT, "Part A start date as YYYY-MM-DD"),
    "recipient.medicare_part_b_start": FieldSpec(RECIPIENT, "Part B start date as YYYY-MM-DD"),
    "recipient.va_rating": FieldSpec(
        RECIPIENT, 'the combined VA disability rating as a whole-number percentage, e.g. "40"', parse=_va_rating),
    "recipient.va_pension_status": FieldSpec(
        RECIPIENT, "only when the letter says they receive it; a rating, pension and health enrollment differ",
        values=("VA pension only", "Aid and Attendance", "Housebound")),
}

# Fail at import, not in production traffic, if the intake schema drifts from these specs.
for _field, _spec in SPECS.items():
    _options = set(QUESTIONS[_field].get("options") or ())
    assert set(_spec.values) <= _options, f"{_field}: values not in schema options"

Person = Literal["caregiver", "recipient", "spouse", "other_household_member", "unclear"]
Period = Literal["weekly", "biweekly", "semimonthly", "monthly", "annual"]
MONTHLY = {"weekly": 52 / 12, "biweekly": 26 / 12, "semimonthly": 2, "monthly": 1, "annual": 1 / 12}
DocumentKind = Literal[
    "paystub", "social_security_letter", "pension_statement", "employer_benefit_document", "tax_return",
    "w2", "form_2441", "medi_cal_notice", "ihss_notice", "medicare_card", "va_letter", "other"]


class _Raw(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    person: Person
    page: int = Field(ge=1)
    evidence: str = Field(max_length=160)
    as_of: str | None = Field(max_length=40)


class RawAnswer(_Raw):
    kind: Literal["answer"]
    field_id: Literal[tuple(SPECS)]  # type: ignore[valid-type]
    value: str = Field(max_length=120)
    tax_year: int | None


class RawIncome(_Raw):
    kind: Literal["member_income"]
    amount: str = Field(max_length=40)
    period: Period


class RawExtraction(BaseModel):
    """What the model must return (strict JSON schema)."""
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    document_kind: DocumentKind  # focuses the model; not returned to the client
    suggestions: list[RawAnswer | RawIncome] = Field(max_length=12)


def prompt_rules() -> str:
    lines = []
    for field_id, spec in SPECS.items():
        line = f"- {field_id} (person: {' or '.join(sorted(spec.people))}): {spec.hint}."
        if spec.values:
            line += " Allowed values: " + ", ".join(json.dumps(v) for v in spec.values) + "."
        if spec.needs_tax_year:
            line += " Set tax_year."
        lines.append(line)
    lines.append('- kind "member_income": gross pay or benefit amount for ONE period as a plain number, with '
                 "period set to the period it covers. Never year-to-date. Any household person.")
    return "\n".join(lines)


def _number(raw: str, field_id: str | None = None) -> float:
    value = float(raw.replace(",", "").replace("$", "").strip())
    rule = (QUESTIONS[field_id].get("validation") if field_id else None) or {}
    if not rule.get("min", 0) <= value <= rule.get("max", 1_000_000_000):
        raise ValueError
    return round(value, 2)


def _parse(field_id: str, spec: FieldSpec, raw: str) -> Any:
    if spec.parse:
        return spec.parse(raw)
    kind = QUESTIONS[field_id]["type"]
    if kind == "single_select":
        if raw not in spec.values:
            raise ValueError
        return raw
    if kind == "multi_select":
        picked = sorted({p.strip() for p in raw.split(";") if p.strip()})
        if not picked or not set(picked) <= set(spec.values):
            raise ValueError
        return picked
    if kind == "number":
        return _number(raw, field_id)
    if kind == "date":
        return date.fromisoformat(raw).isoformat()
    if kind == "boolean" and raw.lower() == "true":
        return True
    raise ValueError


_IDENTIFIERS = [
    re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b"),  # SSN / ITIN
    re.compile(r"\b[1-9][A-Z][A-Z0-9]\d-?[A-Z][A-Z0-9]\d-?[A-Z]{2}\d{2}\b", re.I),  # Medicare MBI
    re.compile(r"\b\d{9,}\b"),  # account / claim numbers
]


def _scrub(text: str) -> str:
    for pattern in _IDENTIFIERS:
        text = pattern.sub("[redacted]", text)
    return text.strip()


def to_suggestion(raw: RawAnswer | RawIncome, pages: int) -> AnswerSuggestion | IncomeSuggestion:
    """A reviewed-ready suggestion, or ValueError when the model output can't be trusted."""
    if raw.page > pages:
        raise ValueError
    source = Source(page=raw.page, evidence=_scrub(raw.evidence), as_of=_scrub(raw.as_of) if raw.as_of else None)
    if isinstance(raw, RawIncome):
        if raw.person == "unclear":
            raise ValueError
        return IncomeSuggestion(person=raw.person, monthly_amount=round(_number(raw.amount) * MONTHLY[raw.period], 2),
                                source=source)
    spec = SPECS[raw.field_id]
    if raw.person not in spec.people:
        raise ValueError
    tax_year = _past_tax_year(str(raw.tax_year)) if spec.needs_tax_year else None
    return AnswerSuggestion(field_id=raw.field_id, value=_parse(raw.field_id, spec, raw.value.strip()),
                            tax_year=tax_year, source=source)


def to_suggestions(raw: RawExtraction, pages: int) -> list[AnswerSuggestion | IncomeSuggestion]:
    out, seen = [], set()
    for item in raw.suggestions:
        try:
            suggestion = to_suggestion(item, pages)
        except (ValueError, TypeError):
            continue
        # Exact repeats collapse; conflicting values are all kept for the caregiver to resolve.
        key = suggestion.model_dump_json(exclude={"source"})
        if key not in seen:
            seen.add(key)
            out.append(suggestion)
    return out
