"""Question groups: what we ask a person, as opposed to what a PDF has boxes for.

A benefits form is not a questionnaire. CCFRM604 has 1081 boxes because it repeats a
person block four times and splits an address across five of them; asking one question
per box is 1074 questions for a single Medi-Cal application. A group is the unit a human
recognises — "where does the person receiving care live?" — and it owns the boxes it
fills:

    QuestionGroup(id="recipient_home_address", prompt="Where do they live?", inputs=[
        GroupInput(key="street", label="Street address", fields=["SOC 295 7"]),
        GroupInput(key="city",   label="City",           fields=["SOC 295 8"]),
    ])

Groups are drafted offline by `app.forms.generate_groups` and committed alongside the
field map, so the split from one answer to several boxes is fixed, reviewable and
covered by tests — nothing interprets the applicant's words at submit time.

Three levers cut the count, in descending order of effect:

* `applies_when` drops a whole group when the profile says it can't apply (the Person 2
  block when the household is one person), so those boxes are never mentioned.
* An input feeding several `fields` collapses boxes that repeat within or across forms.
* `id` is semantic, so the same group drafted for two forms in one program is asked
  once and fills both.
"""

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from ..models import CaseProfile
from .filler import _dig

# `applies_when`, e.g. "household.size >= 2" or "care_recipient.veteran == true".
# A real expression language would be a liability here: these strings are written by a
# model, so the grammar is deliberately too small to express anything surprising.
_CONDITION = re.compile(r"^\s*([a-z_][a-z0-9_.]*)\s*(==|!=|>=|<=|>|<)\s*(.+?)\s*$")

_OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
}

InputType = Literal[
    "short_text", "long_text", "date", "boolean", "single_select", "multi_select"
]


class GroupInput(BaseModel):
    """One thing the applicant types or picks, and the boxes it writes to."""

    key: str = Field(description="Stable identifier, unique within the group")
    label: str = Field(description="What to call this input on screen")
    type: InputType = "short_text"
    fields: list[str] = Field(
        default_factory=list, description="PDF fields this input's value fills"
    )
    options: list[str] = Field(
        default_factory=list, description="Choices, for a select input"
    )
    option_fields: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Option label -> checkbox fields ticked when it is chosen",
    )
    option_values: dict[str, str] = Field(
        default_factory=dict,
        description="Option label -> the export value to write, when it differs",
    )
    required: bool = True
    help: str = ""

    def target_fields(self) -> list[str]:
        """Every PDF field this input can write to, whichever answer is given."""
        targets = list(self.fields)
        for names in self.option_fields.values():
            targets.extend(names)
        return targets


class QuestionGroup(BaseModel):
    """One screen: a question a person understands, plus the inputs it needs."""

    id: str = Field(description="Semantic, stable across forms, e.g. recipient_address")
    prompt: str = Field(description="The question as a person would be asked it")
    help: str = ""
    applies_when: Optional[str] = Field(
        default=None,
        description="Only ask when this holds of the profile, e.g. household.size >= 2",
    )
    opt_in: str = Field(
        default="",
        description="Yes/no question to ask first, for a section that is the "
        "applicant's choice and that the form gives nothing else to gate on",
    )
    inputs: list[GroupInput] = Field(default_factory=list)

    def target_fields(self) -> list[str]:
        return [f for i in self.inputs for f in i.target_fields()]


class SkippedField(BaseModel):
    """A box nobody should be asked about: office use, or filled at signing."""

    field: str
    reason: str


def _literal(raw: str) -> Any:
    text = raw.strip()
    if text[:1] in "'\"" and text[-1:] == text[:1]:
        return text[1:-1]
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("null", "none"):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def parse_condition(expr: str) -> Optional[tuple[str, str, Any]]:
    """`("household.size", ">=", 2)`, or None when the string isn't a condition."""
    match = _CONDITION.match(expr or "")
    if not match:
        return None
    path, op, raw = match.groups()
    # A second operator means a compound expression the grammar can't represent, e.g.
    # "blind == 'Yes' OR impaired == 'Yes'", which would otherwise read as one absurd
    # literal and gate on a value nothing ever equals.
    if any(c in raw for c in "=<>"):
        return None
    return path, op, _literal(raw)


def is_profile_path(path: str) -> bool:
    """Whether a condition reads the profile, as opposed to an earlier answer.

    A group can be gated on something we already know (`household.size >= 2`) or on a
    question asked a moment ago (`past_ihss.received_ihss_before == "Yes"`, the id of
    another group's input). The first is settled here; the second can only be settled
    once the applicant has answered, so it travels to the frontend instead.
    """
    return path.split(".", 1)[0] in CaseProfile.model_fields


def applies(group: QuestionGroup, profile: CaseProfile) -> bool:
    """Whether this group is worth asking, given what we already know.

    An unparseable, answer-dependent or unanswerable condition asks the question. The
    cost of asking something unnecessary is an extra screen; the cost of silently
    skipping it is a blank box on a submitted application.
    """
    if not group.applies_when:
        return True
    parsed = parse_condition(group.applies_when)
    if parsed is None:
        return True
    path, op, expected = parsed
    if not is_profile_path(path):
        return True
    actual = _dig(profile, path)
    if actual is None:
        return True
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            actual = float(actual)
            expected = float(expected)
        except (TypeError, ValueError):
            return True
    elif isinstance(expected, bool):
        actual = bool(actual)
    else:
        actual = str(actual)
        expected = str(expected)
    try:
        return bool(_OPS[op](actual, expected))
    except TypeError:
        return True


def load_groups(schema: dict) -> list[QuestionGroup]:
    return [QuestionGroup.model_validate(g) for g in schema.get("groups") or []]


def load_skips(schema: dict) -> dict[str, str]:
    return {s["field"]: s.get("reason", "") for s in schema.get("skip_fields") or []}


def pdf_values(inp: GroupInput, answer: Any) -> dict[str, str]:
    """The AcroForm values one answer writes, keyed by field.

    The whole point of a group: an answer doesn't go to "the" field, it goes wherever the
    input says — a checkbox per chosen option, a mapped export value, or the same text in
    several boxes across several forms.
    """
    if answer is None or answer == "" or answer == []:
        return {}

    chosen = answer if isinstance(answer, list) else [answer]
    values: dict[str, str] = {}

    if inp.type == "boolean":
        truthy = answer is True or str(answer).strip().lower() in ("true", "yes", "1")
        return {name: "/Yes" if truthy else "/Off" for name in inp.fields}

    for label in (str(c) for c in chosen):
        for name in inp.option_fields.get(label, []):
            values[name] = "/Yes"

    if inp.fields:
        written = [inp.option_values.get(str(c), str(c)) for c in chosen]
        # Only options with a box of their own are excluded from the written value; a
        # plain text input has no options at all and falls through unchanged.
        written = [
            w
            for w, c in zip(written, (str(c) for c in chosen))
            if c not in inp.option_fields
        ]
        if written:
            for name in inp.fields:
                values[name] = ", ".join(written)

    return values
