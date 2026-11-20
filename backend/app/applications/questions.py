"""Turn a program's form fields into the fewest questions, and answers back into PDF values.

Fields that ask for the same fact across forms become one question; each answer is then
written to every box it fills."""

import re
from typing import Any, Optional

from app.applications.state import AppQuestion
from app.cases.models import CaseProfile
from app.forms.groups import GroupInput, applies, is_profile_path, load_groups, load_skips, parse_condition, pdf_values
from app.forms.schema_store import load_schema


def _clean_label(text: str) -> str:
    """Trim a form label/tooltip down to a readable question prompt."""
    text = " ".join((text or "").split())
    # Drop a leading "Section 1 – ..." style prefix, keeping the field's own label.
    for sep in (". ", " - ", " \u2013 "):
        if sep in text and text.lower().startswith("section"):
            text = text.split(sep, 1)[1]
            break
    # The frontend marks optional fields itself, so a label saying so reads twice.
    text = re.sub(r"[\s(]*\(?optional\)?[\s)]*$", "", text, flags=re.I)
    return text.strip()


def build_question(
    field_name: str, label: str, spec_type: str, form_id: str, info
) -> AppQuestion:
    """Compose a single AppQuestion, enriched with the real PDF field type/options."""
    if info is not None:
        qtype = info.intake_type
        options = list(info.options)
    else:
        qtype = _SPEC_TYPE_TO_INTAKE.get(spec_type, "short_text")
        options = []
    return AppQuestion(
        field_id=field_name,
        text=_clean_label(label) or field_name,
        type=qtype,
        required=True,
        options=options,
        form_id=form_id,
        fields=[field_name],
        option_values={o: o for o in options},
    )


_SPEC_TYPE_TO_INTAKE = {
    "text": "short_text",
    "checkbox": "boolean",
    "radio": "single_select",
    "choice": "single_select",
    "date": "short_text",
}


def group_questions(
    form_id: str, profile: CaseProfile, askable: set[str]
) -> tuple[list[AppQuestion], set[str]]:
    """Questions from a form's committed groups, and the fields they account for.

    A group that can't apply to this profile — a second household member's details for a
    one-person household — is dropped whole, so none of its boxes are ever mentioned.
    Fields the group pass marked office-use are accounted for without being asked.
    """
    schema = load_schema(form_id)
    covered: set[str] = set(load_skips(schema))
    questions: list[AppQuestion] = []

    for group in load_groups(schema):
        targets = {f for f in group.target_fields() if f in askable}
        if not targets:
            continue
        covered |= targets
        if not applies(group, profile):
            continue
        parsed = parse_condition(group.applies_when or "")
        ask_when = (
            group.applies_when
            if parsed and not is_profile_path(parsed[0])
            else ""
        )
        # An input whose every box the profile already fills is not a question.
        asking = [i for i in group.inputs if set(i.target_fields()) & askable]
        if not asking:
            continue
        if group.opt_in:
            # A section that is the applicant's choice — naming a representative,
            # picking a dental plan — costs one yes/no unless they want it.
            opt_in_id = f"{group.id}_opt_in"
            questions.append(
                AppQuestion(
                    field_id=f"{opt_in_id}.wanted",
                    text=group.opt_in,
                    type="single_select",
                    options=["Yes", "No"],
                    form_id=form_id,
                    group_id=opt_in_id,
                    input="wanted",
                    ask_when=ask_when,
                )
            )
            ask_when = f'{opt_in_id}.wanted == "Yes"'
        for inp in asking:
            questions.append(
                AppQuestion(
                    field_id=f"{group.id}.{inp.key}",
                    text=_clean_label(inp.label),
                    type=inp.type,
                    required=inp.required,
                    options=list(inp.options),
                    why_this_matters=inp.help or group.help,
                    form_id=form_id,
                    fields=list(inp.fields),
                    option_values=dict(inp.option_values),
                    option_fields={k: list(v) for k, v in inp.option_fields.items()},
                    group_id=group.id,
                    group_prompt=group.prompt,
                    input=inp.key,
                    ask_when=ask_when,
                )
            )
    return questions, covered


def merge_question(existing: AppQuestion, addition: AppQuestion) -> None:
    """Fold a second form's copy of the same question into the one already asked."""
    existing.fields = list(dict.fromkeys([*existing.fields, *addition.fields]))
    for label, names in addition.option_fields.items():
        merged = [*existing.option_fields.get(label, []), *names]
        existing.option_fields[label] = list(dict.fromkeys(merged))
    existing.option_values.update(addition.option_values)
    for label in addition.options:
        if label not in existing.options:
            existing.options.append(label)
    if existing.form_id != addition.form_id:
        existing.form_id = ""  # it now fills more than one form


_RECORD = re.compile(
    r"(person|household\s*member|member|insurance|income|dependent|child|employer|"
    r"applicant|parent|spouse)\s*#?\s*(\d+)|(primary\s+contact)",
    re.I,
)


_NOISE = re.compile(
    r"\([^)]*\)|(?:person|household\s*member|member|insurance|income|dependent|child|"
    r"employer|applicant|parent|spouse)\s*#?\s*\d+|primary\s+contact|"
    r"\b(this|that|their|they|the)\b",
    re.I,
)


_GROUP_SUFFIX = re.compile(r"_(opt_in|profile|details|contact|info)$")


def _record_key(text: str) -> Optional[str]:
    """A `<noun>:<number>` scope from a record marker in `text`, or None.

    "Primary contact" collapses onto person 1 so a form's prose name for the applicant
    and its numbered table row are the same record.
    """
    marker = _RECORD.search(text)
    if not marker:
        return None
    if marker.group(3):  # "primary contact"
        return "person:1"
    noun = marker.group(1).lower().replace(" ", "")
    return f"{noun}:{marker.group(2) or '1'}"


def _scope(question: AppQuestion) -> str:
    """Which record a question is about — the person/policy/source it belongs to.

    Both a group id (`household_member_2`, `insurance_1`, `person_3_profile`) and a
    record marker in the text ("Household member 2", "Other insurance #1") name a
    record, and they must resolve to the *same* key so a loose reprint of a boxed field
    folds into the group that owns it. So both are reduced to `<noun>:<number>`. A
    named block with no numbered record (an address, a representative) is scoped by its
    group id, minus role suffixes so a section and its opt-in agree. A question with
    neither is scoped to the primary record ("").
    """
    if question.group_id:
        keyed = _record_key(question.group_id.replace("_", " "))
        if keyed:
            return keyed
        base = question.group_id
        while True:
            stripped = _GROUP_SUFFIX.sub("", base)
            if stripped == base:
                break
            base = stripped
        return f"g:{base}"
    return _record_key(f"{question.group_prompt} {question.text}") or ""


def _fact(question: AppQuestion) -> tuple[str, str]:
    """What a question asks, and which record it asks it about.

    A form names the same person two ways — "Person 1" in its table, "the Primary
    Contact" in its opening — and labels the same box "Middle name" in one place and
    "Person 1 (Primary Contact) middle name" in another: same record, same fact. But
    "Household member 1" and "Household member 2" are different records, so their
    identically-worded boxes are different facts and must not be merged.
    """
    scope = _scope(question)
    asked = _NOISE.sub(" ", question.text)
    return scope, "".join(c for c in asked.lower() if c.isalnum())


def same_fact(
    question: AppQuestion, asked: list[AppQuestion]
) -> Optional[AppQuestion]:
    """The question already on screen that this one repeats, if there is one."""
    fact = _fact(question)
    if not fact[1]:
        return None
    for other in asked:
        if other.type == question.type and _fact(other) == fact:
            return other
    return None


def to_pdf_value(question: AppQuestion, raw: Any) -> Optional[str]:
    """Translate a user's answer into the concrete AcroForm value pypdf expects."""
    if raw is None or raw == "" or raw == []:
        return None
    if question.type == "boolean":
        truthy = raw is True or str(raw).strip().lower() in ("true", "yes", "1")
        return "/Yes" if truthy else "/Off"
    if question.type in ("single_select", "multi_select"):
        if isinstance(raw, list):
            return ", ".join(question.option_values.get(str(v), str(v)) for v in raw)
        return question.option_values.get(str(raw), str(raw))
    return str(raw)


def grouped_values(question: AppQuestion, raw: Any) -> dict[str, str]:
    """Where a grouped answer lands, using the split declared when the group was drafted."""
    return pdf_values(
        GroupInput(
            key=question.input or question.field_id,
            label=question.text,
            type=question.type,
            fields=question.fields,
            options=question.options,
            option_fields=question.option_fields,
            option_values=question.option_values,
        ),
        raw,
    )
