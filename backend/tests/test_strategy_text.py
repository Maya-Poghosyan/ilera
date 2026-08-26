"""Guards for the strategy the caregiver actually reads.

The routing agent is asked for bullets, but a model reaches for numbered lists, bold headings
and an attribution footer anyway — and that shipped to the results screen as a wall of text.
`format_strategy` is what stands between the model's habits and the caregiver.

Runs with no services. Run directly or via pytest.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.strategy_text import format_strategy, to_bullets  # noqa: E402


def test_numbered_and_bold_lines_become_plain_bullets():
    raw = "1. **Apply for IHSS** through your county office\n2) Then file for Medi-Cal"
    assert to_bullets(raw) == [
        "Apply for IHSS through your county office",
        "Then file for Medi-Cal",
    ]


def test_internal_commentary_never_reaches_the_caregiver():
    raw = (
        "- Apply for IHSS first\n"
        "- The ilera-ihss specialist rated this very likely\n"
        "Attributions: routing agent synthesis\n"
        "- File Form 2441 with your taxes\n"
    )
    assert to_bullets(raw) == ["Apply for IHSS first", "File Form 2441 with your taxes"]


def test_bullet_count_is_capped():
    raw = "\n".join(f"- step {i}" for i in range(25))
    assert len(to_bullets(raw)) == 10


def test_formatting_is_one_bullet_per_line():
    assert format_strategy("1. Do this\n\n2. Then that") == "- Do this\n- Then that"


def test_text_with_nothing_bulletable_is_kept_verbatim():
    """An empty results card would be worse than a wordy one."""
    raw = "The specialists could not agree on an order."
    assert format_strategy(raw) == raw


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
