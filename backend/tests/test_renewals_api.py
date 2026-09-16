"""Multi-renewal: model urgency, CRUD endpoints, back-compat, and access control."""
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import store, auth, records
from app.models import CaseProfile

client = TestClient(app)


def case():
    profile = CaseProfile(id=f"case-{uuid.uuid4().hex}")
    store.save_profile(profile)
    return profile.id


def iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).isoformat()


# --- Derived urgency ------------------------------------------------------


@pytest.mark.parametrize("due_date,expected", [
    (None, "no_date"),
    ("2020-01-01", "overdue"),
    (iso(-1), "overdue"),
    (iso(0), "due_soon"),
    (iso(10), "due_soon"),
    (iso(records.DUE_SOON_DAYS), "due_soon"),
    (iso(records.DUE_SOON_DAYS + 1), "upcoming"),
    (iso(365), "upcoming"),
])
def test_compute_urgency(due_date, expected):
    assert records.compute_urgency(due_date) == expected


def test_urgency_is_serialized_on_item():
    item = records.RenewalItem(case_id="c", program="IHSS", due_date=iso(5))
    dumped = item.model_dump()
    assert dumped["urgency"] == "due_soon"
    # model_dump_json path carries it too (used by the persistence layer).
    assert '"urgency":"due_soon"' in item.model_dump_json().replace(" ", "")


# --- CRUD -----------------------------------------------------------------


def test_create_list_update_delete_renewal():
    case_id = case()
    assert client.get(f"/api/records/renewals/{case_id}").json() == []

    created = client.post("/api/records/renewals", json={
        "case_id": case_id, "program": "Medi-Cal", "due_date": iso(10),
        "status": "pending", "notes": "Packet in the mail", "renewal_period_months": 12,
    })
    assert created.status_code == 201
    item = created.json()
    assert item["program"] == "Medi-Cal"
    assert item["urgency"] == "due_soon"
    assert item["renewal_period_months"] == 12

    listed = client.get(f"/api/records/renewals/{case_id}").json()
    assert len(listed) == 1 and listed[0]["id"] == item["id"]

    updated = client.put(
        f"/api/records/renewals/{item['id']}?case_id={case_id}",
        json={"status": "active", "due_date": iso(200)},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "active"
    assert updated.json()["urgency"] == "upcoming"
    # Untouched fields are preserved by the partial update.
    assert updated.json()["notes"] == "Packet in the mail"

    deleted = client.delete(f"/api/records/renewals/{item['id']}?case_id={case_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/records/renewals/{case_id}").json() == []


def test_multiple_renewals_per_case_sorted_by_due_date():
    case_id = case()
    for program, due in [("VA", iso(90)), ("IHSS", iso(5)), ("PFL", None)]:
        client.post("/api/records/renewals", json={"case_id": case_id, "program": program, "due_date": due})
    programs = [r["program"] for r in client.get(f"/api/records/renewals/{case_id}").json()]
    # Soonest due first; the undated renewal sorts last.
    assert programs == ["IHSS", "VA", "PFL"]


def test_update_and_delete_missing_renewal_returns_404():
    case_id = case()
    assert client.put(f"/api/records/renewals/nope?case_id={case_id}", json={"status": "active"}).status_code == 404
    assert client.delete(f"/api/records/renewals/nope?case_id={case_id}").status_code == 404


@pytest.mark.parametrize("payload", [
    {"program": ""},
    {"due_date": "2026-13-01"},
    {"last_completed_date": "not-a-date"},
    {"renewal_period_months": 0},
    {"renewal_period_months": 121},
])
def test_create_renewal_validation(payload):
    body = {"case_id": case(), "program": "IHSS", **payload}
    assert client.post("/api/records/renewals", json=body).status_code == 422


# --- Back-compat with the legacy single-renewal endpoint ------------------


def test_summary_includes_renewals_list():
    case_id = case()
    client.post("/api/records/renewals", json={"case_id": case_id, "program": "IHSS", "due_date": iso(3)})
    summary = client.get(f"/api/records/{case_id}").json()
    assert "renewals" in summary
    assert "renewal" not in summary  # legacy single-renewal key is gone
    assert summary["renewals"][0]["program"] == "IHSS"
    assert summary["renewals"][0]["urgency"] == "due_soon"


# --- Access control -------------------------------------------------------


def test_renewals_reject_other_users():
    case_id = case()
    owner = auth.User(id=str(uuid.uuid4()), name="Owner", email=f"{uuid.uuid4().hex}@example.com", hashed_password="unused")
    stranger = auth.User(id=str(uuid.uuid4()), name="Stranger", email=f"{uuid.uuid4().hex}@example.com", hashed_password="unused")
    for user in (owner, stranger):
        auth._save_user(user)
    assert store.claim_case(case_id, owner.id)
    owner_headers = {"Authorization": f"Bearer {auth._create_token(owner.id)}"}
    stranger_headers = {"Authorization": f"Bearer {auth._create_token(stranger.id)}"}

    created = client.post("/api/records/renewals", headers=owner_headers, json={"case_id": case_id, "program": "IHSS"})
    assert created.status_code == 201
    item_id = created.json()["id"]

    # A stranger can neither read nor mutate the owner's renewals.
    assert client.get(f"/api/records/renewals/{case_id}", headers=stranger_headers).status_code == 404
    assert client.post("/api/records/renewals", headers=stranger_headers, json={"case_id": case_id, "program": "X"}).status_code == 404
    assert client.put(f"/api/records/renewals/{item_id}?case_id={case_id}", headers=stranger_headers, json={"status": "active"}).status_code == 404
    assert client.delete(f"/api/records/renewals/{item_id}?case_id={case_id}", headers=stranger_headers).status_code == 404
    # The owner still has full access.
    assert client.get(f"/api/records/renewals/{case_id}", headers=owner_headers).status_code == 200
