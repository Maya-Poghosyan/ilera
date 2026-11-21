"""QA: renewals — CRUD, ordering, validation, summary, and access control."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.cases import store
from tests.factories import auth_headers, new_case, new_user

client = TestClient(app)


def iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).isoformat()


# --- Derived urgency ------------------------------------------------------


def test_create_list_update_delete_renewal():
    case_id = new_case()
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
    case_id = new_case()
    for program, due in [("VA", iso(90)), ("IHSS", iso(5)), ("PFL", None)]:
        client.post("/api/records/renewals", json={"case_id": case_id, "program": program, "due_date": due})
    programs = [r["program"] for r in client.get(f"/api/records/renewals/{case_id}").json()]
    # Soonest due first; the undated renewal sorts last.
    assert programs == ["IHSS", "VA", "PFL"]


def test_update_and_delete_missing_renewal_returns_404():
    case_id = new_case()
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
    body = {"case_id": new_case(), "program": "IHSS", **payload}
    assert client.post("/api/records/renewals", json=body).status_code == 422


def test_summary_includes_renewals_list():
    case_id = new_case()
    client.post("/api/records/renewals", json={"case_id": case_id, "program": "IHSS", "due_date": iso(3)})
    summary = client.get(f"/api/records/{case_id}").json()
    assert "renewals" in summary
    assert summary["renewals"][0]["program"] == "IHSS"
    assert summary["renewals"][0]["urgency"] == "due_soon"


# --- Access control -------------------------------------------------------


def test_renewals_reject_other_users():
    case_id = new_case()
    owner = new_user("Owner")
    stranger = new_user("Stranger")
    assert store.claim_case(case_id, owner.id)
    owner_headers = auth_headers(owner)
    stranger_headers = auth_headers(stranger)

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
