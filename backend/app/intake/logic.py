"""Visibility and input validation for the current topic-based intake contract."""
from datetime import date
from math import isfinite
from typing import Any

from .schema import SCREENS

UNKNOWN = {"I'm not sure", "Prefer not to answer", "Not sure"}
QUESTIONS = {q["field_id"]: q for section in SCREENS for q in section["questions"]}
from .household import details as household_details, valid_members


def answer_context(answers: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """Derived values never masquerade as user answers or survive cleared inputs."""
    context = dict(answers)
    for prefix in ("recipient", "caregiver"):
        context.pop(prefix + ".age", None)
        try:
            birth = date.fromisoformat(str(answers.get(prefix + ".date_of_birth", "")))
            now = today or date.today()
            if birth <= now:
                context[prefix + ".age"] = now.year - birth.year - ((now.month, now.day) < (birth.month, birth.day))
        except ValueError:
            pass
    context.update(household_details(answers))
    filing = answers.get('recipient.tax_filing_status')
    context['tax.recipient_joint_return'] = ('Yes' if filing == 'Yes, jointly with a spouse' else 'No' if filing in ['Yes, their own return', 'No'] else None)
    if answers.get('caregiver.claims_recipient') is True:
        context['recipient.claimed_as_dependent'] = 'Yes'
        context['recipient.dependent_claimant_relationship'] = {
            'Parent': 'Adult child', 'Child': 'Parent', 'Spouse or domestic partner': 'Spouse',
            'Parent-in-law': 'Other relative', 'Sibling': 'Other relative',
            'Grandparent': 'Other relative', 'Grandchild': 'Other relative',
            'Other relative': 'Other relative', 'Friend': 'Someone else',
            'Neighbor': 'Someone else', 'Other': 'Someone else',
        }.get(answers.get('caregiver.relationship'))
    combined = answers.get("recipient.coverage_and_benefits")
    if isinstance(combined, list):
        coverage = {"Medicaid", "Medicare", "VA health care", "Employer or private insurance", "No health coverage", "Other"}
        context["recipient.health_coverage"] = [x for x in combined if x in coverage or x in UNKNOWN]
        context["recipient.current_benefits"] = [x for x in combined if x not in coverage]
    context["recipient.medicaid_status"] = "Enrolled now" if answers.get("recipient.medicaid_covered") is True else None
    if answers.get("caregiver.coresidence") == "Yes":
        for part in ("street", "city", "state", "county", "zip"):
            context[f"recipient.address.{part}"] = answers.get(f"caregiver.address.{part}")
    return context


def answered(value: Any) -> bool:
    return bool(value.strip()) if isinstance(value, str) else value is not None and value != []


def visible(condition: dict | None, answers: dict[str, Any]) -> bool:
    if not condition:
        return True
    if "any" in condition:
        return any(visible(c, answers) for c in condition["any"])
    if "all" in condition:
        return all(visible(c, answers) for c in condition["all"])
    if "not" in condition:
        return not visible(condition["not"], answers)
    raw, expected, op = answers.get(condition["field"]), condition.get("value"), condition["op"]
    if op == "answered":
        return answered(raw)
    if op == "blank":
        return not answered(raw)
    if op == "equals":
        return raw == expected
    if op == "not_equals":
        return raw != expected
    if op == "in":
        return isinstance(expected, list) and raw in expected
    if op == "includes":
        return isinstance(raw, list) and expected in raw
    if op == "includes_any":
        return isinstance(raw, list) and isinstance(expected, list) and any(v in raw for v in expected)
    if op in {"gte", "lte", "gt", "lt"}:
        if isinstance(raw, bool) or raw is None or raw == "":
            return False
        try:
            number = float(raw)
            if not isfinite(number):
                return False
            return {"gte": number >= expected, "lte": number <= expected,
                    "gt": number > expected, "lt": number < expected}[op]
        except (ValueError, TypeError):
            return False
    raise ValueError(f"Unsupported intake condition: {op}")


def clean_answers(answers: dict[str, Any]) -> dict[str, Any]:
    """Remove obsolete fields and stale answers on branches that no longer apply."""
    result = {k: v for k, v in answers.items() if k in QUESTIONS}
    for key, value in list(result.items()):
        aliases = QUESTIONS[key].get("answer_aliases", {})
        if isinstance(value, list) and aliases:
            result[key] = list(dict.fromkeys(aliases.get(item, item) for item in value if isinstance(item, str) and aliases.get(item, item) is not None))
        if isinstance(value, str) and value in aliases:
            if aliases[value] is None:
                result.pop(key)
            else:
                result[key] = aliases[value]
    members=result.get("household.members")
    if isinstance(members,list):
        keep=[]
        for m in members:
            if not isinstance(m,dict):keep.append(m);continue
            if m.get('kind')=='spouse' and result.get('recipient.marital_status')!='Yes':continue
            if m.get('kind')=='caregiver' and result.get('recipient.marital_status')=='Yes' and result.get('caregiver.relationship')=='Spouse or domestic partner':continue
            keep.append(m)
        result['household.members']=keep
    programs=result.get('recipient.programs_touched',[])
    for key in ['recipient.program_statuses','case.program_dates']:
        if isinstance(result.get(key),dict):result[key]={p:v for p,v in result[key].items() if p in programs}
    covered=result.get('recipient.coverage_and_benefits')
    if result.get('recipient.medicaid_covered') is True:
        if not isinstance(covered,list):result['recipient.coverage_and_benefits']=['Medicaid']
        elif 'Medicaid' not in covered:result['recipient.coverage_and_benefits']=[x for x in covered if x not in UNKNOWN]+['Medicaid']
    while True:
        context = answer_context(result)
        active = {k: v for k, v in result.items() if visible(QUESTIONS[k].get("show_when"), context)}
        if active == result:
            return active
        result = active


def validate_answers(answers: dict[str, Any], *, complete: bool = False) -> dict[str, Any]:
    unknown = set(answers) - QUESTIONS.keys()
    if unknown:
        raise ValueError("Unknown intake fields")
    cleaned = clean_answers(answers)
    context = answer_context(cleaned)
    for key, question in QUESTIONS.items():
        if not visible(question.get("show_when"), context):
            continue
        value = cleaned.get(key)
        if not answered(value):
            if complete and question["required"]:
                raise ValueError(f"Missing answer: {key}")
            continue
        kind = question["type"]
        if kind == "household_members":
            if not valid_members(value, cleaned):
                raise ValueError(f"Invalid household details: {key}")
            continue
        if kind in {"program_statuses", "program_dates"}:
            programs = cleaned.get("recipient.programs_touched", [])
            if not isinstance(value, dict) or not programs or set(value) != set(programs):
                raise ValueError(f"Incomplete program details: {key}")
            for entry in value.values():
                if kind == "program_statuses":
                    if not isinstance(entry,str) or entry not in question["options"]:
                        raise ValueError(f"Invalid program status: {key}")
                elif entry != "I'm not sure":
                    try: date.fromisoformat(entry)
                    except (ValueError, TypeError): raise ValueError(f"Invalid program date: {key}") from None
            continue
        allowed = set(question.get("options", []))
        if question.get("allow_not_sure"):
            allowed.add("I'm not sure")
        if question.get("allow_prefer_not_to_answer"):
            allowed.add("Prefer not to answer")
        if isinstance(value, str) and value in UNKNOWN:
            if value in allowed:
                continue
            raise ValueError(f"Unsupported uncertainty answer: {key}")
        if kind == "single_select" and (not isinstance(value, str) or value not in allowed):
            raise ValueError(f"Invalid choice: {key}")
        if kind in {"multi_select", "tag_input"}:
            if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
                raise ValueError(f"Invalid selections: {key}")
            if kind == "multi_select" and any(v not in allowed for v in value):
                raise ValueError(f"Invalid choice: {key}")
            exclusive = question.get("validation", {}).get("exclusive_options", [])
            if len(value) != len(set(value)) or len(value) > 1 and any(v in exclusive for v in value):
                raise ValueError(f"Conflicting selections: {key}")
            if any(all(item in value for item in pair) for pair in question.get("validation", {}).get("incompatible_options", [])):
                raise ValueError(f"Conflicting coverage: {key}")
        elif kind == "boolean" and type(value) is not bool:
            raise ValueError(f"Invalid boolean: {key}")
        elif kind == "number":
            limits = question.get("validation", {})
            if type(value) not in (int, float) or not isfinite(value):
                raise ValueError(f"Invalid number: {key}")
            if (limits.get("integer") and value != int(value)
                    or value < limits.get("min", -float("inf")) or value > limits.get("max", float("inf"))):
                raise ValueError(f"Number outside limits: {key}")
        elif kind == "date":
            try:
                parsed = date.fromisoformat(value)
                if key in {"recipient.date_of_birth", "caregiver.date_of_birth", "recipient.lpr_since"} and parsed > date.today():
                    raise ValueError("Future birth or immigration status date")
            except (ValueError, TypeError):
                raise ValueError(f"Invalid date: {key}") from None
        elif kind == "zip" and (not isinstance(value, str) or len(value) != 5 or not value.isdigit()):
            raise ValueError(f"Invalid ZIP: {key}")
        elif kind == "state_dropdown" and (not isinstance(value, str) or value not in set(question.get('options') or {
                'AL','AK','AZ','AR','CA','CO','CT','DE','DC','FL','GA','HI','ID','IL','IN','IA','KS','KY',
                'LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH',
                'OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY'})):
            raise ValueError(f"Invalid state: {key}")
        elif kind in {"short_text", "long_text"} and not isinstance(value, str):
            raise ValueError(f"Invalid text: {key}")
    return cleaned
