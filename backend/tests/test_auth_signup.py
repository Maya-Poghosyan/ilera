"""Signup happens after the strategy is shown, so it is where the caregiver's phone number and
their anonymous case both arrive."""

import uuid

from fastapi.testclient import TestClient

from app import store
from app.main import app
from app.models import CaseProfile

client = TestClient(app)


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


def _anonymous_case() -> str:
    profile = CaseProfile(id=f"case-{uuid.uuid4().hex}")
    store.save_profile(profile)
    return profile.id


def test_signup_stores_phone_and_claims_the_case() -> None:
    case_id = _anonymous_case()
    email = _email()
    res = client.post(
        "/api/auth/signup",
        json={
            "name": "Ada Caregiver",
            "email": email,
            "password": "hunter2!",
            "phone": "555-0100",
            "case_id": case_id,
        },
    )
    assert res.status_code == 201, res.text
    user = res.json()["user"]
    assert user["phone"] == "555-0100"

    # The contact details the government forms need now live on the case.
    profile = store.get_profile(case_id)
    assert profile is not None
    assert profile.caregiver.email == email
    assert profile.caregiver.phone == "555-0100"
    assert store.get_case_id_for_user(user["id"]) == case_id


def test_signup_survives_a_stale_case_id() -> None:
    res = client.post(
        "/api/auth/signup",
        json={
            "name": "Ada Caregiver",
            "email": _email(),
            "password": "hunter2!",
            "phone": "555-0100",
            "case_id": "case-does-not-exist",
        },
    )
    assert res.status_code == 201, res.text
    assert store.get_case_id_for_user(res.json()["user"]["id"]) is None
