"""Round-trip tests for the Postgres-backed stores.

With TEST_DATABASE_URL set (any Postgres; pgvector not required) these run against the
database, creating their tables on first use. Without it they exercise the in-memory
fallback instead, so they are worth running either way.
Run directly (`python tests/test_postgres_store.py`) or via pytest if installed.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")

from fastapi import HTTPException  # noqa: E402

from app import access, applications, auth, preferences, records, reminders, store  # noqa: E402
from app import suggested_events as events  # noqa: E402
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


def _case() -> str:
    case_id = f"case-{uuid.uuid4().hex}"
    store.save_profile(CaseProfile(id=case_id))
    return case_id


def test_a_case_starts_unowned_and_is_claimed_once():
    user = _user(f"owner+{uuid.uuid4().hex}@example.com")
    auth._save_user(user)
    case_id = _case()
    # Anonymous intake: nobody owns it yet, so holding the id is enough.
    assert store.get_case_owner(case_id) is None

    assert store.claim_case(case_id, user.id) is True
    assert store.get_case_owner(case_id) == user.id
    assert store.get_case_id_for_user(user.id) == case_id
    # Idempotent for the owner, refused for everyone else — a guessed id can't be adopted.
    assert store.claim_case(case_id, user.id) is True
    other = _user(f"thief+{uuid.uuid4().hex}@example.com")
    auth._save_user(other)
    assert store.claim_case(case_id, other.id) is False
    assert store.get_case_owner(case_id) == user.id
    assert store.get_case_id_for_user(other.id) is None


def test_claiming_a_case_that_does_not_exist_fails():
    user = _user(f"noc+{uuid.uuid4().hex}@example.com")
    auth._save_user(user)
    assert store.claim_case(f"case-{uuid.uuid4().hex}", user.id) is False


def test_case_access_allows_unowned_and_the_owner_only():
    owner = _user(f"acc+{uuid.uuid4().hex}@example.com")
    stranger = _user(f"str+{uuid.uuid4().hex}@example.com")
    auth._save_user(owner)
    auth._save_user(stranger)
    case_id = _case()

    access.authorize_case(case_id, None)  # unowned: the anonymous creator can still work
    store.claim_case(case_id, owner.id)
    access.authorize_case(case_id, owner)
    for caller in (None, stranger):
        try:
            access.authorize_case(case_id, caller)
            raise AssertionError(f"{caller} should not reach a claimed case")
        except HTTPException as exc:
            assert exc.status_code == 404


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


def test_reminder_crud():
    reminder = reminders.Reminder(
        kind=reminders.ReminderKind.custom,
        message="Submit the timesheet",
        schedule=reminders.ReminderSchedule(freq=reminders.ScheduleFreq.once),
    )
    reminders.save_reminder(reminder)
    assert reminders.get_reminder(reminder.id).message == "Submit the timesheet"
    assert any(r.id == reminder.id for r in reminders.list_reminders())
    assert reminders.delete_reminder(reminder.id) is True
    assert reminders.get_reminder(reminder.id) is None
    assert reminders.delete_reminder(reminder.id) is False


def test_timekeeping_and_journal_are_scoped_by_case():
    case_id = f"case-{uuid.uuid4().hex}"
    other = f"case-{uuid.uuid4().hex}"
    entry = records.TimekeepingEntry(case_id=case_id, date="2026-02-01", hours=3.5)
    records.save_timekeeping(entry)
    journal = records.JournalEntry(case_id=case_id, date="2026-02-01", text="Good day")
    records.save_journal(journal)

    assert [e.id for e in records.list_timekeeping(case_id)] == [entry.id]
    assert records.list_timekeeping(other) == []
    assert [e.id for e in records.list_journal(case_id)] == [journal.id]
    assert records.list_journal(other) == []
    # An id belonging to another case must not be readable or deletable through it.
    assert records.get_timekeeping(entry.id, other) is None
    assert records.delete_timekeeping(entry.id, other) is False
    assert records.delete_timekeeping(entry.id, case_id) is True
    assert records.delete_journal(journal.id, case_id) is True


def test_renewal_and_preferences_are_keyed_by_case():
    case_id = f"case-{uuid.uuid4().hex}"
    assert records.get_renewal(case_id) is None
    records.save_renewal(records.RenewalInfo(case_id=case_id, due_date="2026-06-01"))
    records.save_renewal(records.RenewalInfo(case_id=case_id, due_date="2026-07-01"))
    renewal = records.get_renewal(case_id)
    assert renewal is not None and renewal.due_date == "2026-07-01"

    assert preferences.get_preferences(case_id).monitor_inboxes is False
    preferences.save_preferences(
        preferences.Preferences(case_id=case_id, monitor_inboxes=True)
    )
    assert preferences.get_preferences(case_id).monitor_inboxes is True


def test_application_state_is_keyed_by_case_and_program():
    case_id = f"case-{uuid.uuid4().hex}"
    applications.save_app_state(
        applications.ApplicationState(case_id=case_id, program="IHSS")
    )
    applications.save_app_state(
        applications.ApplicationState(
            case_id=case_id, program="CFRA / FMLA", status=applications.AppStatus.completed
        )
    )
    assert applications.get_app_state(case_id, "IHSS").status == applications.AppStatus.open
    # Programs with spaces and slashes share a case without colliding.
    assert (
        applications.get_app_state(case_id, "CFRA / FMLA").status
        == applications.AppStatus.completed
    )
    assert len(applications.list_app_states(case_id)) == 2
    assert applications.list_app_states(f"case-{uuid.uuid4().hex}") == []


def test_suggested_event_crud():
    event = events.SuggestedEvent(date="2026-03-04", title="Neurology follow-up")
    events.save_suggested_event(event)
    assert events.get_suggested_event(event.id).title == "Neurology follow-up"
    assert any(e.id == event.id for e in events.list_suggested_events())
    assert events.delete_suggested_event(event.id) is True
    assert events.get_suggested_event(event.id) is None


if __name__ == "__main__":
    from app import db  # noqa: E402

    print("backend:", "postgres" if db.available() else "in-memory")
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
