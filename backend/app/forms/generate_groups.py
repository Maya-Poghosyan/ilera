"""Second offline pass: turn a form's unfilled boxes into questions worth asking.

`app.forms.generate` decides what each box means and which of them the profile can
already answer. What's left would otherwise be shown to the applicant one box at a time
— 1074 screens for Medi-Cal. This pass reads the same pages again and returns, for every
box the profile can't fill, either the group it belongs to or a reason nobody should be
asked about it (office use, filled at signing).

    pip install -r requirements-band.txt
    python -m app.forms.generate_groups ccfrm604 --dry-run

The output is committed next to the field map, so what an applicant types and where it
lands is fixed at review time rather than decided live. Validation is the same idea as
in the mapping pass — the model retries against its own errors — and here it enforces
that every unfilled box is accounted for exactly once, that a select's options really
are that widget's export values, and that an `applies_when` condition parses.

Groups merge across pages, and across forms in a program, by `id`. A model that names
the same idea `recipient_home_address` on page 2 of SOC-295 and page 1 of SOC-426A gets
one question filling both.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from typing import Optional

from pydantic import BaseModel, Field

from .discovery import is_junk
from .extract import extract_fields, extract_pages
from .filler import SCHEMA_DIR, _get_pdf_path, load_schema
from .generate import _describe_field, _model
from .groups import (
    GroupInput,
    QuestionGroup,
    SkippedField,
    is_profile_path,
    parse_condition,
)
from .profile_paths import profile_paths

SYSTEM_PROMPT = """\
You turn the leftover fields of a US government benefits form into the smallest set of \
questions that could fill them.

The app already knows the applicant's basic details and has filled every field it can. \
You are given, one page at a time, the page's printed text and the fields still unfilled.

Group them the way a person would answer, not the way the form is laid out:
- One group is one thing a person knows: an address, a date of birth, an employer. Its \
`prompt` is what you would say out loud to ask for it.
- Inside a group, one `input` per value the applicant has to give. An address is one \
group with street/city/state/ZIP inputs, not four questions.
- One input may fill several `fields` when the same value belongs in several boxes.
- A row of checkboxes that are alternatives is ONE `single_select` input, or a \
`multi_select` when several can be true, with `option_fields` giving the box each choice \
ticks. Never ask about them one at a time.
- Give `applies_when` when a whole group only matters for some applicants, so it can be \
skipped. Exactly one comparison: `<path> <op> <value>`, never `and`/`or`. The path is \
either one of the profile paths listed below — `household.size >= 2` for a second \
household member, `care_recipient.veteran == true` — or `<group id>.<input key>` of an \
earlier group on this page, which is how you express a form's "if yes, ..." follow-ups: \
`past_ihss.received_ihss_before == "Yes"`.
- Put a field in `skip` when no applicant should ever be asked it, rather than making a \
group for it. Anything the printed text marks "for county use only", "for staff use", \
"do not write in this space", a worker/agency name, an office date stamp, or an \
instruction that happens to be fillable. Also every signature line and the date beside \
it: the form is signed by hand once printed. Leave them blank on the form.
- `id` must describe the content, in snake_case, and must be the same string whenever \
the same information is asked on another page or another form: `recipient_home_address`, \
`provider_date_of_birth`. This is what lets one answer fill several forms.

Every field you are given must appear exactly once, in a group or in `skip`.
"""


class PageGroups(BaseModel):
    groups: list[QuestionGroup] = Field(default_factory=list)
    skip: list[SkippedField] = Field(default_factory=list)


def _askable(form_id: str) -> list[str]:
    """Fields the map leaves for the applicant: no profile path, so nothing fills them."""
    fields = load_schema(form_id).get("fields") or {}
    return [
        name
        for name, spec in fields.items()
        if isinstance(spec, dict) and not spec.get("profile_path")
    ]


def _page_prompt(form_id: str, page: dict, fields: list[dict], labels: dict[str, str]) -> str:
    described = []
    for field in fields:
        line = _describe_field(field)
        label = labels.get(field["name"])
        if label:
            line += f' means: "{label}"'
        described.append(line)
    return (
        f"Form: {form_id.upper()}  (page {page['page']})\n\n"
        f"--- printed page text ---\n{page['text'].strip()}\n\n"
        "--- fields still unfilled on this page ---\n"
        + "\n".join(described)
        + "\n\n--- profile paths usable in applies_when ---\n"
        + ", ".join(sorted(profile_paths()))
        + "\n\nGroup every field listed above, or skip it."
    )


def _normalized(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())


def _repair_names(output: PageGroups, fields: list[dict]) -> None:
    """Fix field names that differ from the real one only in punctuation or case.

    Forms name sibling widgets `Pg1-13` and `Pg1_13`, and a model transcribing dozens of
    them per page will occasionally normalise one. Correcting an unambiguous near-miss in
    place is deterministic; anything that doesn't resolve to exactly one real field is
    left alone for the validator to reject.
    """
    real = {f["name"] for f in fields}
    candidates: dict[str, list[str]] = {}
    for name in real:
        candidates.setdefault(_normalized(name), []).append(name)

    def fix(name: str) -> str:
        if name in real:
            return name
        matches = candidates.get(_normalized(name), [])
        return matches[0] if len(matches) == 1 else name

    for group in output.groups:
        for inp in group.inputs:
            inp.fields = [fix(n) for n in inp.fields]
            inp.option_fields = {
                label: [fix(n) for n in names]
                for label, names in inp.option_fields.items()
            }
    for skipped in output.skip:
        skipped.field = fix(skipped.field)


def _validate(output: PageGroups, fields: list[dict]) -> list[str]:
    """Reasons the draft can't be committed, phrased for the model to correct."""
    by_name = {f["name"]: f for f in fields}
    known_paths = set(profile_paths())
    answer_paths = {
        f"{g.id}.{i.key}" for g in output.groups for i in g.inputs
    }
    errors: list[str] = []
    seen: dict[str, str] = {}

    def claim(name: str, by: str) -> None:
        if name not in by_name:
            errors.append(f'"{name}" is not an unfilled field on this page')
        elif name in seen:
            errors.append(f'"{name}" is claimed by both {seen[name]} and {by}')
        else:
            seen[name] = by

    for group in output.groups:
        where = f"group {group.id}"
        if group.applies_when:
            parsed = parse_condition(group.applies_when)
            if parsed is None:
                errors.append(
                    f"{where}: applies_when {group.applies_when!r} is not a single "
                    "comparison <path> <op> <value>, e.g. household.size >= 2"
                )
            elif is_profile_path(parsed[0]):
                if parsed[0] not in known_paths:
                    errors.append(
                        f"{where}: applies_when reads {parsed[0]!r}, which is not one of "
                        "the profile paths given"
                    )
            elif parsed[0] not in answer_paths:
                # A gate on nothing is silently ignored at runtime, so the group would
                # be asked of everyone: reject it rather than let it look like gating.
                errors.append(
                    f"{where}: applies_when reads {parsed[0]!r}, which is neither a "
                    "profile path nor <group id>.<input key> of a group on this page"
                )
        if not group.inputs:
            errors.append(f"{where}: has no inputs")
        keys: set[str] = set()
        for inp in group.inputs:
            if inp.key in keys:
                errors.append(f'{where}: two inputs share the key "{inp.key}"')
            keys.add(inp.key)

            selecting = inp.type in ("single_select", "multi_select")
            if selecting and not inp.options:
                errors.append(f"{where}.{inp.key}: a select input needs options")
            for label in [*inp.option_fields, *inp.option_values]:
                if label not in inp.options:
                    errors.append(
                        f'{where}.{inp.key}: "{label}" is not one of its options '
                        f"{inp.options}"
                    )
            for name in inp.target_fields():
                claim(name, f"{where}.{inp.key}")

            # Every choice has to end up somewhere: either it ticks a box of its own, or
            # it writes a value the widget will accept. A radio silently ignores anything
            # outside its export values, so "Male" on a /1,/2 widget leaves it unset.
            for label in inp.options:
                if label in inp.option_fields:
                    continue
                if not inp.fields:
                    errors.append(
                        f'{where}.{inp.key}: option "{label}" ticks no field and the '
                        "input writes to none either"
                    )
                    continue
                written = inp.option_values.get(label, label)
                for name in inp.fields:
                    allowed = (by_name.get(name) or {}).get("options") or []
                    if allowed and written not in allowed:
                        errors.append(
                            f'{where}.{inp.key}: option "{label}" writes "{written}" to '
                            f'"{name}", whose export values are {allowed}; give '
                            "option_values mapping each option to one of those, or "
                            "option_fields if each choice has its own box"
                        )

    for skipped in output.skip:
        claim(skipped.field, "skip")
        if not skipped.reason.strip():
            errors.append(f'"{skipped.field}": skipping needs a reason')

    unaccounted = [name for name in by_name if name not in seen]
    if unaccounted:
        errors.append(f"not grouped and not skipped: {unaccounted}")
    return errors


_SIGNATURE = re.compile(r"signature|signed by|initials", re.I)


def skip_signatures(
    groups: list[QuestionGroup], skip: list[SkippedField], fields: dict[str, dict]
) -> list[QuestionGroup]:
    """Stop asking people to type a signature.

    A signature is made by hand on the printed form, and the date beside it is the date
    it was signed — neither is an answer anyone can give here, so those boxes are left
    blank and their screens disappear.
    """
    already = {s.field for s in skip}
    kept: list[QuestionGroup] = []
    for group in groups:
        inputs: list[GroupInput] = []
        for inp in group.inputs:
            signed = _SIGNATURE.search(f"{group.prompt} {inp.label} {inp.key}") or any(
                (fields.get(name) or {}).get("type") == "signature"
                for name in inp.target_fields()
            )
            if not signed:
                inputs.append(inp)
                continue
            for name in inp.target_fields():
                if name not in already:
                    already.add(name)
                    skip.append(
                        SkippedField(
                            field=name, reason="signed by hand on the printed form"
                        )
                    )
        if inputs:
            group.inputs = inputs
            kept.append(group)
    return kept


def dedupe_targets(groups: list[QuestionGroup]) -> list[QuestionGroup]:
    """Leave each field to one group, dropping later claims on it.

    Pages are drafted independently, so a person block spread over two pages can come
    back as `person_1_overview` and `person_1_details` both claiming the first-name box.
    Whichever group reached it first keeps it; the other loses that target, and an input
    or group left with nothing to fill disappears — it was a second way of asking a
    question already on the list.
    """
    owned: set[str] = set()
    kept: list[QuestionGroup] = []
    for group in groups:
        inputs: list[GroupInput] = []
        for inp in group.inputs:
            inp.fields = [f for f in inp.fields if f not in owned]
            inp.option_fields = {
                label: [f for f in names if f not in owned]
                for label, names in inp.option_fields.items()
            }
            inp.option_fields = {k: v for k, v in inp.option_fields.items() if v}
            targets = inp.target_fields()
            if not targets:
                continue
            owned |= set(targets)
            inputs.append(inp)
        if inputs:
            group.inputs = inputs
            kept.append(group)
    return kept


_PERSON = re.compile(r"^person_(\d+)_")


def gate_person_blocks(groups: list[QuestionGroup]) -> None:
    """Ask about the second, third and fourth person only if they exist.

    Forms that repeat a person block are drafted a page at a time, so whether the block
    is the second or the fourth is visible on some pages and not others. `person_3_*`
    says it plainly, and a three-person household is never asked the fourth block's
    ~30 questions.
    """
    for group in groups:
        match = _PERSON.match(group.id)
        if not match or group.applies_when:
            continue
        nth = int(match.group(1))
        if nth > 1:
            group.applies_when = f"household.size >= {nth}"


def repair_conditions(groups: list[QuestionGroup]) -> None:
    """Point every `applies_when` at something real, or drop it.

    A gate is validated per page, but the question it depends on can be phrased loosely
    (`patient_is_family_member` for the group of that name, `provider.tier2_convicted`
    for an input key) or refer to nothing at all. A condition that resolves to nothing is
    worse than none: it reads like gating and gates nothing, so it is rewritten when the
    referent is unambiguous and removed when it isn't — which asks the question, the safe
    direction.
    """
    known = set(profile_paths())
    exact = {f"{g.id}.{i.key}" for g in groups for i in g.inputs}
    by_group = {g.id: g for g in groups}
    by_key: dict[str, list[str]] = {}
    for group in groups:
        for inp in group.inputs:
            by_key.setdefault(inp.key, []).append(f"{group.id}.{inp.key}")

    for group in groups:
        if not group.applies_when:
            continue
        parsed = parse_condition(group.applies_when)
        if parsed is None:
            group.applies_when = None
            continue
        path, op, raw = parsed
        if path in exact or (is_profile_path(path) and path in known):
            continue

        target = by_group.get(path)
        if target is not None and len(target.inputs) == 1:
            resolved = f"{target.id}.{target.inputs[0].key}"
        else:
            matches = by_key.get(path.rsplit(".", 1)[-1], [])
            resolved = matches[0] if len(matches) == 1 else ""
        if resolved and resolved != f"{group.id}.{group.inputs[0].key}":
            literal = f'"{raw}"' if isinstance(raw, str) else str(raw).lower()
            group.applies_when = f"{resolved} {op} {literal}"
        else:
            group.applies_when = None


def _merge(into: dict[str, QuestionGroup], drafted: list[QuestionGroup]) -> None:
    """Fold a page's groups into the form's, joining on `id` then on input key."""
    for group in drafted:
        existing = into.get(group.id)
        if existing is None:
            into[group.id] = group.model_copy(deep=True)
            continue
        by_key = {i.key: i for i in existing.inputs}
        for inp in group.inputs:
            current = by_key.get(inp.key)
            if current is None:
                existing.inputs.append(inp.model_copy(deep=True))
                continue
            current.fields = list(dict.fromkeys([*current.fields, *inp.fields]))
            for label, names in inp.option_fields.items():
                merged = [*current.option_fields.get(label, []), *names]
                current.option_fields[label] = list(dict.fromkeys(merged))
            for label in inp.options:
                if label not in current.options:
                    current.options.append(label)
            current.option_values.update(inp.option_values)


async def generate_groups(
    form_id: str, only_pages: Optional[list[int]] = None
) -> tuple[list[QuestionGroup], list[SkippedField]]:
    """Draft the question groups for one form, one page per model call."""
    from pydantic_ai import Agent, ModelRetry

    pdf_path = _get_pdf_path(form_id)
    if not pdf_path:
        raise FileNotFoundError(f"No PDF on disk for form {form_id}")

    schema = load_schema(form_id)
    labels = {
        name: spec.get("label", "")
        for name, spec in (schema.get("fields") or {}).items()
        if isinstance(spec, dict)
    }
    askable = set(_askable(form_id))
    fields_by_name = {
        f["name"]: f
        for f in extract_fields(pdf_path)
        if not is_junk(f) and f["name"] in askable
    }

    agent = Agent(_model(), output_type=PageGroups, system_prompt=SYSTEM_PROMPT, retries=5)
    current_fields: list[dict] = []

    @agent.output_validator
    def check(output: PageGroups) -> PageGroups:
        _repair_names(output, current_fields)
        errors = _validate(output, current_fields)
        if errors:
            raise ModelRetry(
                "Fix these and return the whole page again:\n- " + "\n- ".join(errors)
            )
        return output

    merged: dict[str, QuestionGroup] = {}
    skipped: dict[str, SkippedField] = {}
    for page in extract_pages(pdf_path):
        if only_pages and page["page"] not in only_pages:
            continue
        page_fields = [fields_by_name[n] for n in page["fields"] if n in fields_by_name]
        if not page_fields:
            continue
        current_fields = page_fields

        result = await agent.run(_page_prompt(form_id, page, page_fields, labels))
        _merge(merged, result.output.groups)
        for s in result.output.skip:
            skipped.setdefault(s.field, s)
        print(
            f"  page {page['page']}: {len(page_fields)} unfilled -> "
            f"{len(result.output.groups)} groups, {len(result.output.skip)} skipped",
            file=sys.stderr,
        )

    groups = dedupe_targets(list(merged.values()))
    skip = list(skipped.values())
    groups = skip_signatures(groups, skip, fields_by_name)
    gate_person_blocks(groups)
    repair_conditions(groups)
    return groups, skip


def write_groups(
    form_id: str, groups: list[QuestionGroup], skip: list[SkippedField]
) -> str:
    schema = load_schema(form_id)
    schema["groups"] = [
        g.model_dump(exclude_defaults=True, exclude_none=True) for g in groups
    ]
    schema["skip_fields"] = [s.model_dump() for s in skip]
    path = os.path.join(SCHEMA_DIR, f"{form_id.lower()}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("form_id")
    parser.add_argument("--pages", help="Comma-separated page numbers (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Print instead of writing")
    args = parser.parse_args()

    only = [int(p) for p in args.pages.split(",")] if args.pages else None
    groups, skip = asyncio.run(generate_groups(args.form_id, only))
    inputs = sum(len(g.inputs) for g in groups)
    print(
        f"{args.form_id}: {len(groups)} groups ({inputs} inputs), {len(skip)} skipped",
        file=sys.stderr,
    )

    if args.dry_run:
        print(json.dumps({
            "groups": [g.model_dump(exclude_defaults=True, exclude_none=True) for g in groups],
            "skip_fields": [s.model_dump() for s in skip],
        }, indent=2, ensure_ascii=False))
        return
    print(f"wrote {write_groups(args.form_id, groups, skip)}", file=sys.stderr)


if __name__ == "__main__":
    main()
