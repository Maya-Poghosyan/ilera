"""Targeted tests for the Band eligibility store layer and match-level projection.

Runs against the in-memory (no-database) store fallback, so it needs no services.
Run directly (`python tests/test_band_store.py`) or via pytest if installed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import store  # noqa: E402
from app.models import CaseProfile, SpecialistFinding  # noqa: E402


def _fresh_case() -> str:
    profile = CaseProfile(id="case-test-1")
    store.save_profile(profile)
    return profile.id


def test_room_case_mapping_roundtrip():
    store.map_room_to_case("room-abc", "case-xyz")
    assert store.get_case_for_room("room-abc") == "case-xyz"
    assert store.get_case_for_room("room-unknown") is None


def test_match_level_projection():
    # Every 5-level match maps to a legacy (status, confidence) pair, ordered by strength.
    levels = ["none", "low", "medium", "likely", "very_likely"]
    confidences = []
    for lvl in levels:
        r = store.finding_to_result(SpecialistFinding(program="IHSS", match_level=lvl))
        confidences.append(r.confidence)
        assert r.match_level == lvl
    assert confidences == sorted(confidences), "confidence should increase with match strength"


def test_record_finding_persists_and_projects():
    case_id = _fresh_case()
    store.map_room_to_case("room-1", case_id)
    returned = store.record_finding(
        "room-1", "ihss", "IHSS", "likely",
        ["Meets ADL need", "CA resident"], ["medical"], ["ihss.txt"],
    )
    assert returned == case_id
    p = store.get_profile(case_id)
    assert p is not None
    finding = p.findings["ihss"]
    assert finding.complete is True
    assert finding.match_level == "likely"
    assert finding.cross_programs == ["medical"]
    # Projected into the legacy eligibility shape the results page consumes.
    assert p.eligibility["IHSS"].match_level == "likely"
    assert "ihss.txt" in p.eligibility["IHSS"].sources


def test_record_finding_unknown_room_is_noop():
    assert store.record_finding("nope", "ihss", "IHSS", "low", [], [], []) is None


def test_record_strategy_marks_complete():
    case_id = _fresh_case()
    store.map_room_to_case("room-2", case_id)
    returned = store.record_strategy("room-2", "Apply for IHSS first, then Medi-Cal.")
    assert returned == case_id
    p = store.get_profile(case_id)
    assert p is not None
    assert p.strategy_complete is True
    assert p.band_status == "complete"
    assert "IHSS" in p.strategy


def test_record_strategy_unknown_room_is_noop():
    assert store.record_strategy("nope", "x") is None


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
