"""Round-trip tests for the Postgres-backed user and case stores.

Needs a database: point TEST_DATABASE_URL at one (any Postgres, pgvector not required)
and the tests create their tables on first use. Without it they are skipped.
Run directly (`python tests/test_postgres_store.py`) or via pytest if installed.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DSN = os.environ.get("TEST_DATABASE_URL", "")
os.environ["DATABASE_URL"] = DSN

from app import auth, db, store  # noqa: E402
from app.models import CaseProfile  # noqa: E402


def _user(email: str) -> auth.User:
    return auth.User(
        id=str(uuid.uuid4()),
        name="Ada",
        email=email,
        hashed_password="hash",
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_user_roundtrip_and_email_lookup():
    user = _user(f"Ada+{uuid.uuid4().hex}@Example.COM")
    auth._save_user(user)
    assert auth._get_user_by_id(user.id) is not None
    # Emails are matched case-insensitively, however they were typed on either side.
    found = auth._get_user_by_email(user.email.upper())
    assert found is not None and found.id == user.id


def test_user_case_link_is_updated_in_place():
    user = _user(f"link+{uuid.uuid4().hex}@example.com")
    auth._save_user(user)
    user.case_id = "case-123"
    auth._save_user(user)
    stored = auth._get_user_by_id(user.id)
    assert stored is not None and stored.case_id == "case-123"


def test_case_profile_roundtrip():
    case_id = f"case-{uuid.uuid4().hex}"
    profile = CaseProfile(id=case_id)
    profile.caregiver.name = "Grace"
    store.save_profile(profile)
    loaded = store.get_profile(case_id)
    assert loaded is not None and loaded.caregiver.name == "Grace"
    assert store.get_profile("case-missing") is None


def test_room_case_mapping_roundtrip():
    room = f"room-{uuid.uuid4().hex}"
    store.map_room_to_case(room, "case-xyz")
    assert store.get_case_for_room(room) == "case-xyz"
    store.map_room_to_case(room, "case-abc")
    assert store.get_case_for_room(room) == "case-abc"
    assert store.get_case_for_room("room-unknown") is None


if __name__ == "__main__":
    if not DSN:
        print("SKIP: set TEST_DATABASE_URL to run the Postgres store tests")
        sys.exit(0)
    assert db.available()
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
