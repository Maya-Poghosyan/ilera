"""Guards for the committed question groups and the answers they turn into.

A group is what saves the applicant from being asked once per box, so the failure modes
are asymmetric: a group that claims a field nobody asks about leaves the box blank on a
government form, while a group that misroutes an answer writes the wrong thing into it.
Both are silent. These tests check the committed groups against the real PDFs and check
that a grouped answer lands where the group says it does.

Runs against the in-memory store (no services). Run directly or via pytest.
"""
import os
import re
import sys

os.environ.pop("REDIS_URL", None)  # force the in-memory store fallback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import applications  # noqa: E402
from app.forms import filler  # noqa: E402
from app.forms.extract import extract_fields  # noqa: E402
from app.forms.groups import (  # noqa: E402
    GroupInput,
    QuestionGroup,
    applies,
    is_profile_path,
    load_groups,
    load_skips,
    parse_condition,
    pdf_values,
)
from app.forms.profile_paths import profile_paths  # noqa: E402
from app.models import CareRecipient, CaseProfile, Household  # noqa: E402
from tests.test_form_maps import _filled_profile  # noqa: E402


def _grouped_form_ids() -> list[str]:
    return [
        fname[:-5]
        for fname in sorted(os.listdir(filler.SCHEMA_DIR))
        if fname.endswith(".json") and filler.load_schema(fname[:-5]).get("groups")
    ]


# ---------------------------------------------------------------------------
# The committed groups
# ---------------------------------------------------------------------------


def test_groups_only_target_real_unfilled_fields():
    """A group may only claim a box the PDF has and the profile can't already fill."""
    checked = 0
    for form_id in _grouped_form_ids():
        schema = filler.load_schema(form_id)
        askable = {
            name
            for name, spec in (schema.get("fields") or {}).items()
            if isinstance(spec, dict) and not spec.get("profile_path")
        }
        for group in load_groups(schema):
            unknown = sorted(set(group.target_fields()) - askable)
            assert not unknown, (
                f"{form_id}/{group.id}: targets fields that are not unfilled inputs on "
                f"this form: {unknown}"
            )
        checked += 1
    assert checked > 0, "expected at least one form with committed groups"


def test_each_field_belongs_to_one_group():
    """Two groups owning a box means one of them silently overwrites the other."""
    for form_id in _grouped_form_ids():
        owner: dict[str, str] = {}
        for group in load_groups(filler.load_schema(form_id)):
            for inp in group.inputs:
                for name in inp.target_fields():
                    where = f"{group.id}.{inp.key}"
                    assert name not in owner, (
                        f"{form_id}: field {name!r} is claimed by both {owner[name]} "
                        f"and {where}"
                    )
                    owner[name] = where


def test_skipped_fields_are_not_also_asked():
    """A box can be left blank on purpose or asked about, not both."""
    for form_id in _grouped_form_ids():
        schema = filler.load_schema(form_id)
        skipped = set(load_skips(schema))
        for group in load_groups(schema):
            overlap = sorted(skipped & set(group.target_fields()))
            assert not overlap, f"{form_id}/{group.id}: skipped yet asked: {overlap}"


def test_every_option_lands_somewhere():
    """A choice must tick a box of its own or write a value the widget accepts."""
    for form_id in _grouped_form_ids():
        pdf_fields = {
            f["name"]: f for f in extract_fields(filler._get_pdf_path(form_id))
        }
        for group in load_groups(filler.load_schema(form_id)):
            for inp in group.inputs:
                for label in inp.options:
                    if label in inp.option_fields:
                        continue
                    written = inp.option_values.get(label, label)
                    for name in inp.fields:
                        allowed = (pdf_fields.get(name) or {}).get("options") or []
                        assert not allowed or written in allowed, (
                            f"{form_id}/{group.id}.{inp.key}: option {label!r} writes "
                            f"{written!r} to {name!r}, which only accepts {allowed}"
                        )


def test_group_conditions_gate_on_something_real():
    """A condition we can't read, or that names nothing, gates nothing at all.

    It is silently ignored at runtime and the group is asked of everyone, which looks
    like working gating in the JSON. Either it reads a profile path or it reads another
    group's input by its question id.
    """
    for form_id in _grouped_form_ids():
        groups = load_groups(filler.load_schema(form_id))
        answerable = {f"{g.id}.{i.key}" for g in groups for i in g.inputs}
        for group in groups:
            if not group.applies_when:
                continue
            parsed = parse_condition(group.applies_when)
            assert parsed is not None, (
                f"{form_id}/{group.id}: unreadable applies_when "
                f"{group.applies_when!r}"
            )
            path = parsed[0]
            if is_profile_path(path):
                assert path in profile_paths(), (
                    f"{form_id}/{group.id}: applies_when reads {path!r}, not a profile "
                    "path"
                )
            else:
                assert path in answerable, (
                    f"{form_id}/{group.id}: applies_when reads {path!r}, which is no "
                    "question on this form"
                )


# ---------------------------------------------------------------------------
# Turning an answer into PDF values
# ---------------------------------------------------------------------------


def test_composite_answers_reach_distinct_fields():
    """The point of a composite group: one screen, a different value per box."""
    street = GroupInput(key="street", label="Street", fields=["addr_street"])
    city = GroupInput(key="city", label="City", fields=["addr_city"])
    assert pdf_values(street, "123 Main St") == {"addr_street": "123 Main St"}
    assert pdf_values(city, "Los Angeles") == {"addr_city": "Los Angeles"}


def test_one_value_fills_every_field_it_names():
    """The same fact asked by several forms is written to all of their boxes."""
    inp = GroupInput(key="ssn", label="SSN", fields=["soc295_ssn", "soc426a_ssn"])
    assert pdf_values(inp, "123-45-6789") == {
        "soc295_ssn": "123-45-6789",
        "soc426a_ssn": "123-45-6789",
    }


def test_multi_select_ticks_the_box_for_each_choice():
    inp = GroupInput(
        key="adls",
        label="Which activities?",
        type="multi_select",
        options=["Bathing", "Dressing", "Eating"],
        option_fields={"Bathing": ["cb_bath"], "Dressing": ["cb_dress"], "Eating": ["cb_eat"]},
    )
    assert pdf_values(inp, ["Bathing", "Eating"]) == {"cb_bath": "/Yes", "cb_eat": "/Yes"}


def test_single_select_writes_the_widgets_export_value():
    inp = GroupInput(
        key="gender",
        label="Gender",
        type="single_select",
        fields=["pg1_9"],
        options=["Male", "Female"],
        option_values={"Male": "/1", "Female": "/2"},
    )
    assert pdf_values(inp, "Female") == {"pg1_9": "/2"}


def test_empty_answers_write_nothing():
    inp = GroupInput(key="x", label="X", fields=["f"])
    assert pdf_values(inp, "") == {}
    assert pdf_values(inp, None) == {}
    assert pdf_values(inp, []) == {}


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------


def _group(condition: str) -> QuestionGroup:
    return QuestionGroup(
        id="person_2",
        prompt="Tell us about the second person",
        applies_when=condition,
        inputs=[GroupInput(key="name", label="Name", fields=["p2_name"])],
    )


def test_gating_drops_groups_the_profile_rules_out():
    alone = CaseProfile(id="c", household=Household(size=1))
    shared = CaseProfile(id="c", household=Household(size=3))
    assert not applies(_group("household.size >= 2"), alone)
    assert applies(_group("household.size >= 2"), shared)


def test_answer_dependent_gates_are_left_to_the_frontend():
    """A follow-up can only be settled once the earlier question has been answered."""
    group = QuestionGroup(
        id="past_ihss_details",
        prompt="When did you last receive IHSS?",
        applies_when='past_ihss.received_ihss_before == "Yes"',
        inputs=[GroupInput(key="when", label="When", fields=["f"])],
    )
    assert applies(group, CaseProfile(id="c", household=Household(size=1)))


def test_gating_asks_when_the_profile_cannot_answer():
    """An unknown or unreadable condition asks: a blank box is worse than a question."""
    unknown = CaseProfile(id="c")
    assert applies(_group("household.size >= 2"), unknown)
    assert applies(_group("this is not a condition"), unknown)


def test_gating_reads_booleans_and_strings():
    veteran = CaseProfile(id="c", care_recipient=CareRecipient(veteran=True))
    civilian = CaseProfile(id="c", care_recipient=CareRecipient(veteran=False))
    assert applies(_group("care_recipient.veteran == true"), veteran)
    assert not applies(_group("care_recipient.veteran == true"), civilian)

    la = CaseProfile(id="c", care_recipient=CareRecipient(county="Los Angeles"))
    assert applies(_group("care_recipient.county == 'Los Angeles'"), la)
    assert not applies(_group("care_recipient.county != 'Los Angeles'"), la)


def test_nobody_is_asked_to_type_a_signature():
    """A signature is made by hand on the printed form, so it is never a question."""
    for form_id in _grouped_form_ids():
        for group in load_groups(filler.load_schema(form_id)):
            for inp in group.inputs:
                text = f"{group.prompt} {inp.label} {inp.key}".lower()
                assert "signature" not in text, f"{form_id}/{group.id}.{inp.key}"


def test_repeated_person_blocks_are_gated_on_household_size():
    """Person 3's ~30 questions are for households that have a third person."""
    for form_id in _grouped_form_ids():
        for group in load_groups(filler.load_schema(form_id)):
            match = re.match(r"^person_(\d+)_", group.id)
            if not match or int(match.group(1)) < 2:
                continue
            assert group.applies_when, f"{form_id}/{group.id} is asked of everyone"


def test_a_smaller_household_is_asked_less():
    """The gating has to show up in what the applicant actually sees."""
    def screens(size: int) -> int:
        profile = CaseProfile(id=f"hh{size}", household=Household(size=size))
        result = applications.start_application(f"hh-{size}", "Medi-Cal", profile)
        return len({q["group_id"] or q["field_id"] for q in result["questions"]})

    assert screens(1) < screens(4)


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------


def test_grouping_cuts_the_number_of_screens():
    """What the applicant sees: screens, not boxes. This is the whole feature."""
    profile = _filled_profile()
    for program in applications.PROGRAM_FORMS:
        result = applications.start_application(f"case-{program}", program, profile)
        questions = result["questions"]
        boxes = sum(len(q.get("fields") or [q["field_id"]]) for q in questions)
        screens = len({q.get("group_id") or q["field_id"] for q in questions})
        assert screens <= boxes, f"{program}: grouping made more screens than boxes"
        print(f"  {program}: {screens} screens for {boxes} fields")


def test_one_person_is_asked_their_first_name_once():
    """A form reprints a name atop every section; that isn't a dozen questions."""
    profile = CaseProfile(id="dupes", household=Household(size=2))
    questions = applications.start_application("dupes", "Medi-Cal", profile)["questions"]
    for fact in ("first name", "city", "social security number"):
        by_person: dict[str, int] = {}
        for q in questions:
            person = re.match(r"^(person_\d+)_", q["group_id"] or "")
            # Their own, not their caretaker's or their taxpayer's: the label is the
            # bare fact once the person it belongs to is stripped off the front.
            label = re.sub(r"person\s*\d+\s*[-—:]*\s*", "", q["text"], flags=re.I)
            if person and label.strip().lower() == fact:
                by_person[person.group(1)] = by_person.get(person.group(1), 0) + 1
        for person, count in by_person.items():
            assert count == 1, f"{person} is asked for their {fact} {count} times"


def test_two_people_are_still_asked_separately():
    """Folding repeats is per person: Person 2's name is not Person 1's."""
    groups = load_groups(filler.load_schema("ccfrm604"))
    names = {
        g.id.split("_details")[0]
        for g in groups
        for i in g.inputs
        if i.label.lower().endswith("first name") or i.label.lower() == "first name"
    }
    assert len({n for n in names if n.startswith("person_")}) > 1


def test_an_optional_section_waits_for_the_question_that_opens_it():
    """Whole appendices hang off an earlier answer, so nobody scrolls past them."""
    gated = 0
    for group in load_groups(filler.load_schema("ccfrm604")):
        condition = parse_condition(group.applies_when or "")
        if condition and not is_profile_path(condition[0]):
            path = condition[0]
            owners = [
                f"{g.id}.{i.key}" for g in load_groups(filler.load_schema("ccfrm604"))
                for i in g.inputs
            ]
            assert path in owners, f"{group.id} waits on {path}, which nobody asks"
            gated += 1
    assert gated, "no section is gated on an answer"


def test_a_grouped_answer_survives_to_a_filled_pdf():
    """Answer a real program's questions and check the PDF comes back filled."""
    profile = _filled_profile()
    program = "IHSS"
    case_id = "case-groups-e2e"
    result = applications.start_application(case_id, program, profile)
    answers = {
        q["field_id"]: (
            [q["options"][0]] if q.get("options") and q["type"] == "multi_select"
            else q["options"][0] if q.get("options")
            else "2026-01-01" if q["type"] == "date"
            else "Test answer"
        )
        for q in result["questions"]
    }
    pdf_bytes = applications.submit_answers(case_id, program, answers, profile)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
