"""Scope-aware dedup: distinct records must not collapse, real reprints still fold.

The loose-field dedup in `applications._same_fact` folds a box a form reprints (the
applicant's name atop a section) into the question already asked. Its correctness turns
on `_scope`: two identically-worded boxes are the same question only when they are about
the same *record*. "Household member 1" and "Household member 2" are different people;
"Other insurance #1" and "#2" are different policies. Collapsing them drops a box on a
submitted government form — silent and wrong. These guard that boundary.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import applications  # noqa: E402
from app.applications import AppQuestion, _fact, _scope, _same_fact  # noqa: E402
from app.models import CaseProfile, Household  # noqa: E402


def q(field_id: str, text: str, group_id: str = "", prompt: str = "", type: str = "short_text") -> AppQuestion:
    return AppQuestion(field_id=field_id, text=text, type=type, group_id=group_id, group_prompt=prompt)


# ---------------------------------------------------------------------------
# Distinct records must never merge
# ---------------------------------------------------------------------------


def test_household_members_are_distinct_records():
    a = q("f1", "Social Security Number", group_id="household_member_1")
    b = q("f2", "Social Security Number", group_id="household_member_2")
    assert _scope(a) != _scope(b)
    assert _fact(a) != _fact(b)
    assert _same_fact(b, [a]) is None


def test_numbered_insurance_policies_are_distinct():
    a = q("f1", "Is this insurance through your employment?", group_id="insurance_1", type="single_select")
    b = q("f2", "Is this insurance through your employment?", group_id="insurance_2", type="single_select")
    assert _fact(a) != _fact(b)
    assert _same_fact(b, [a]) is None


def test_numbered_records_in_free_text_are_distinct():
    # No group id: the record marker lives in the visible label instead.
    a = q("f1", "Person 1 middle name")
    b = q("f2", "Person 2 middle name")
    assert _fact(a) != _fact(b)
    assert _same_fact(b, [a]) is None


def test_a_recipients_own_field_is_not_a_household_members():
    recipient = q("f1", "Social Security Number", group_id="recipient_social_security_number")
    member = q("f2", "Social Security Number", group_id="household_member_1")
    assert _fact(recipient) != _fact(member)


# ---------------------------------------------------------------------------
# The same record's reprints still fold
# ---------------------------------------------------------------------------


def test_a_reprinted_box_folds_into_the_group_that_owns_it():
    grouped = q("g1", "Middle name", group_id="person_1_profile", prompt="About you")
    reprint = q("l1", "Person 1 (Primary Contact) middle name")
    assert _scope(grouped) == _scope(reprint) == "person:1"
    assert _fact(grouped) == _fact(reprint)
    assert _same_fact(reprint, [grouped]) is grouped


def test_primary_contact_is_the_first_person():
    numbered = q("f1", "First name", group_id="person_1_profile")
    named = q("f2", "Primary Contact first name")
    assert _fact(numbered) == _fact(named)


def test_a_group_and_its_opt_in_share_a_scope():
    section = q("f1", "Their name", group_id="authorized_representative_contact")
    opt_in = q("f2", "Do you want a representative?", group_id="authorized_representative_contact_opt_in")
    assert _scope(section) == _scope(opt_in)


# ---------------------------------------------------------------------------
# End to end: no program collapses distinct records
# ---------------------------------------------------------------------------


def test_no_program_collapses_distinct_records():
    """Distinct records stay separate across every program's composed questions.

    `_same_fact` only ever folds a question into one from a *different* group (a loose
    reprint into the group that owns the box); inputs within a single group are distinct
    by construction. So a genuine collapse is two questions with the same scope+fact+type
    coming from different groups. This asserts that never happens for a mapped program.
    """
    profile = CaseProfile(id="e2e", household=Household(size=4))
    for program in applications.PROGRAM_FORMS:
        result = applications.start_application(f"scope-{program}", program, profile)
        seen: dict[tuple, tuple[str, str]] = {}
        for raw in result["questions"]:
            question = AppQuestion(**raw)
            fact = _fact(question)
            if not fact[1]:
                continue
            key = (question.type, fact)
            prior = seen.get(key)
            if prior is not None and prior[0] != question.group_id:
                raise AssertionError(
                    f"{program}: {prior[1]} (group {prior[0]!r}) and "
                    f"{question.field_id} (group {question.group_id!r}) share a "
                    f"scope+fact across groups and would be wrongly merged"
                )
            seen[key] = (question.group_id, question.field_id)


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
