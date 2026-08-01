"""Guards for the `profile_path` vocabulary offered to the form-map generator.

`app.forms.profile_paths` decides which `CaseProfile` fields a form map is allowed to
reference. Its hand-maintained `_NOT_COLLECTED` exclusion list is the fragile part: if
intake starts collecting one of those fields, the vocabulary silently stays short and
forms keep asking the user for something we already have; if intake *stops* populating
an offered path, PDFs silently print blank instead of asking. Both directions are
checked here by mapping a synthetic, fully-answered intake.

Runs against the in-memory store (no services). Run directly or via pytest.
"""
import os
import sys

os.environ.pop("REDIS_URL", None)  # force the in-memory store fallback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.forms.filler import _dig  # noqa: E402
from app.forms.profile_paths import _NOT_COLLECTED, profile_paths  # noqa: E402
from app.intake import schema as intake_schema  # noqa: E402
from app.intake.mapping import map_answers_to_profile  # noqa: E402
from app.models import CaseProfile  # noqa: E402

# Answers that have to be specific for the derivation under test to produce a value;
# everything else is filled generically from the question's declared type/options.
_PINNED: dict[str, object] = {
    "recipient.date_of_birth": "1950-06-15",
    "caregiver.address.state": "CA",
    "caregiver.address.zip": "90001",
    "caregiver.address.county": "Los Angeles",
    "recipient.household_size": 3,
}

# Option labels that mean "no answer" — picking one would leave the profile field unset.
_NON_ANSWERS = {"I'm not sure", "Prefer not to answer", "None of these", "None of the above"}


def _all_questions() -> list[dict]:
    schema = intake_schema.build_schema()
    questions: list[dict] = []
    for screen in schema["screens"]:
        questions.extend(screen["questions"])
    for module in schema["mini_modules"]:
        questions.extend(module["questions"])
    questions.extend(schema["contact_screen"]["questions"])
    return questions


def _synthetic_answer(question: dict) -> object:
    options = [o for o in (question.get("options") or []) if o not in _NON_ANSWERS]
    qtype = question["type"]
    if qtype == "multi_select":
        return options[:2] or ["Other"]
    if qtype == "single_select":
        return options[0] if options else "Yes"
    if qtype == "boolean":
        return True
    if qtype == "number":
        return 2
    if qtype == "date":
        return "2020-01-01"
    if qtype == "state_dropdown":
        return "CA"
    if qtype == "zip":
        return "90001"
    return f"test {question['field_id']}"


def _fully_answered_profile() -> CaseProfile:
    answers: dict[str, object] = {}
    for question in _all_questions():
        answers[question["field_id"]] = _synthetic_answer(question)
    answers.update(_PINNED)
    profile = CaseProfile(id="case-profile-paths")
    map_answers_to_profile(answers, profile)
    return profile


def test_offered_paths_are_populated_by_intake():
    """Every path the generator may use must actually receive a value."""
    profile = _fully_answered_profile()
    empty = [p for p in profile_paths() if _dig(profile, p) in (None, "", [])]
    assert not empty, (
        "offered as a profile_path but never populated by a complete intake — a form "
        f"mapped to one of these would silently print blank: {empty}"
    )


def test_excluded_paths_stay_uncollected():
    """The exclusion list must not outlive the gap it describes."""
    profile = _fully_answered_profile()
    now_collected = [p for p in sorted(_NOT_COLLECTED) if _dig(profile, p) not in (None, "", [])]
    assert not now_collected, (
        "intake now populates these, so they should be offered to the form-map "
        f"generator instead of excluded: {now_collected}"
    )


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
