"""Tests for Care Calendar review (milestone §5): review-status persistence, idempotent
acceptance of suggestions into calendar events, and owner isolation.

With TEST_DATABASE_URL set these run against Postgres; otherwise they exercise the
in-memory fallback. Run directly (`python tests/test_calendar_review.py`) or via pytest.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")

from fastapi import HTTPException  # noqa: E402

from app import auth, main, store  # noqa: E402
from app import calendar_events as cal  # noqa: E402
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


def _owned_case(user: auth.User) -> str:
    case_id = f"case-{uuid.uuid4().hex}"
    store.save_profile(CaseProfile(id=case_id))
    store.claim_case(case_id, user.id)
    return case_id


def _suggestion(user: auth.User, case_id: str, **kw) -> events.SuggestedEvent:
    event = events.SuggestedEvent(
        title=kw.get("title", "Neurology follow-up"),
        date=kw.get("date", "2026-03-04"),
        source="email",
        user_id=user.id,
        case_id=case_id,
        confidence=kw.get("confidence", 0.9),
        action_required=kw.get("action_required"),
    )
    events.save_suggested_event(event)
    return event


def test_accept_persists_status_and_creates_calendar_event():
    user = _user(f"a+{uuid.uuid4().hex}@example.com")
    auth._save_user(user)
    case_id = _owned_case(user)
    suggestion = _suggestion(user, case_id)

    updated = main.api_review_suggested_event(
        suggestion.id, main.SuggestedEventReview(status="accepted"), user=user
    )
    assert updated.status == "accepted"
    # The status change is durable, not just returned.
    assert events.get_suggested_event(suggestion.id).status == "accepted"

    accepted = cal.list_calendar_events(user_id=user.id)
    assert len(accepted) == 1
    assert accepted[0].title == suggestion.title
    assert accepted[0].source_suggestion_id == suggestion.id
    assert accepted[0].source == "email"


def test_accept_is_idempotent():
    user = _user(f"idem+{uuid.uuid4().hex}@example.com")
    auth._save_user(user)
    case_id = _owned_case(user)
    suggestion = _suggestion(user, case_id)

    for _ in range(3):
        main.api_review_suggested_event(
            suggestion.id, main.SuggestedEventReview(status="accepted"), user=user
        )
    # Re-accepting must not create duplicate calendar events.
    assert len(cal.list_calendar_events(user_id=user.id)) == 1


def test_dismiss_removes_calendar_event():
    user = _user(f"dis+{uuid.uuid4().hex}@example.com")
    auth._save_user(user)
    case_id = _owned_case(user)
    suggestion = _suggestion(user, case_id)

    main.api_review_suggested_event(
        suggestion.id, main.SuggestedEventReview(status="accepted"), user=user
    )
    assert len(cal.list_calendar_events(user_id=user.id)) == 1
    # Changing the mind: dismiss should pull it off the calendar.
    main.api_review_suggested_event(
        suggestion.id, main.SuggestedEventReview(status="dismissed"), user=user
    )
    assert events.get_suggested_event(suggestion.id).status == "dismissed"
    assert cal.list_calendar_events(user_id=user.id) == []


def test_review_and_calendar_are_owner_isolated():
    owner = _user(f"own+{uuid.uuid4().hex}@example.com")
    stranger = _user(f"str+{uuid.uuid4().hex}@example.com")
    auth._save_user(owner)
    auth._save_user(stranger)
    case_id = _owned_case(owner)
    suggestion = _suggestion(owner, case_id)

    # A stranger cannot review someone else's suggestion.
    try:
        main.api_review_suggested_event(
            suggestion.id, main.SuggestedEventReview(status="accepted"), user=stranger
        )
        raise AssertionError("stranger should not review another user's suggestion")
    except HTTPException as exc:
        assert exc.status_code == 404
    assert events.get_suggested_event(suggestion.id).status == "pending"

    # Owner accepts, then the stranger must not see or delete the calendar event.
    main.api_review_suggested_event(
        suggestion.id, main.SuggestedEventReview(status="accepted"), user=owner
    )
    assert cal.list_calendar_events(user_id=stranger.id) == []
    accepted = cal.list_calendar_events(user_id=owner.id)[0]
    try:
        main.api_delete_calendar_event(accepted.id, user=stranger)
        raise AssertionError("stranger should not delete another user's calendar event")
    except HTTPException as exc:
        assert exc.status_code == 404
    assert len(cal.list_calendar_events(user_id=owner.id)) == 1


def test_delete_suggestion_also_removes_accepted_calendar_event():
    user = _user(f"del+{uuid.uuid4().hex}@example.com")
    auth._save_user(user)
    case_id = _owned_case(user)
    suggestion = _suggestion(user, case_id)

    main.api_review_suggested_event(
        suggestion.id, main.SuggestedEventReview(status="accepted"), user=user
    )
    assert len(cal.list_calendar_events(user_id=user.id)) == 1
    main.api_delete_suggested_event(suggestion.id, user=user)
    assert events.get_suggested_event(suggestion.id) is None
    assert cal.list_calendar_events(user_id=user.id) == []


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
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
