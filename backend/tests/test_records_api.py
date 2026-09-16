"""Records validation, editing, incident review, and reminder isolation."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import store, auth
from app.models import CaseProfile

client = TestClient(app)


def case():
    profile = CaseProfile(id=f"case-{uuid.uuid4().hex}")
    store.save_profile(profile)
    return profile.id


@pytest.mark.parametrize("changes", [
    {"hours": -1}, {"hours": 25}, {"date": "2026-02-30"},
    {"service_type": "invalid"}, {"start_time": "25:00"},
    {"start_time": "09:00"},
    {"start_time": "09:00", "end_time": "10:00", "hours": 2},
])
def test_timekeeping_validation(changes):
    payload = {"case_id": case(), "date": "2026-09-16", "hours": 1, **changes}
    assert client.post("/api/records/timekeeping", json=payload).status_code == 422


def test_edit_timekeeping_entry():
    case_id = case()
    payload = {"case_id": case_id, "date": "2026-09-16", "hours": 1}
    created = client.post("/api/records/timekeeping", json=payload).json()
    response = client.put(f"/api/records/timekeeping/{created['id']}", json={**payload, "hours": 2})
    assert response.status_code == 200
    assert response.json()["hours"] == 2
    assert response.json()["created_at"] == created["created_at"]
    assert client.put(f"/api/records/timekeeping/{created['id']}", json={**payload, "case_id": case()}).status_code == 404


def test_incident_review_and_edit_reset():
    case_id = case()
    payload = {"case_id": case_id, "date": "2026-09-16", "text": "No fall today"}
    entry = client.post("/api/records/journal", json=payload).json()
    url = f"/api/records/journal/{entry['id']}"
    reviewed = client.patch(f"{url}/incident?case_id={case_id}", json={"status": "dismissed"})
    assert reviewed.status_code == 200
    assert reviewed.json()["incident_status"] == "dismissed"
    assert client.put(url, json=payload).json()["incident_status"] == "dismissed"
    changed = client.put(url, json={**payload, "text": "She fell today"}).json()
    assert changed["incident_status"] == "unreviewed"
    assert client.post("/api/records/journal", json={**payload, "text": "  "}).status_code == 422
    assert client.patch(f"{url}/incident?case_id={case()}", json={"status": "confirmed"}).status_code == 404


def test_records_sorted_by_care_date():
    case_id = case()
    for date in ("2026-09-16", "2026-09-01", "2026-09-20"):
        client.post("/api/records/journal", json={"case_id": case_id, "date": date, "text": "Care note"})
    entries = client.get(f"/api/records/journal/{case_id}").json()
    assert [entry["date"] for entry in entries] == ["2026-09-20", "2026-09-16", "2026-09-01"]


def test_owned_reminders_and_records_reject_other_users():
    case_id = case()
    user = auth.User(id=str(uuid.uuid4()), name="Caregiver", email=f"{uuid.uuid4().hex}@example.com", hashed_password="unused")
    auth._save_user(user)
    assert store.claim_case(case_id, user.id)
    headers = {"Authorization": f"Bearer {auth._create_token(user.id)}"}
    created = client.post("/api/reminders", headers=headers, json={"case_id": case_id, "message": "Private"})
    assert created.status_code == 201
    reminder_id = created.json()["id"]
    assert client.get("/api/reminders").json() == []
    assert client.get(f"/api/reminders?case_id={case_id}").status_code == 404
    assert client.get(f"/api/reminders/{reminder_id}").status_code == 404
    assert client.patch(f"/api/reminders/{reminder_id}", json={"active": False}).status_code == 404
    assert client.delete(f"/api/reminders/{reminder_id}").status_code == 404
    assert client.get("/api/reminders", headers=headers).json()[0]["id"] == reminder_id
    assert client.get(f"/api/records/journal/{case_id}").status_code == 404
    assert client.delete(f"/api/reminders/{reminder_id}", headers=headers).status_code == 200


def test_authenticated_stranger_cannot_edit_owned_records():
    case_id = case()
    payload = {"case_id": case_id, "date": "2026-09-16", "hours": 1}
    entry = client.post("/api/records/timekeeping", json=payload).json()
    owner = auth.User(id=str(uuid.uuid4()), name="Owner", email=f"{uuid.uuid4().hex}@example.com", hashed_password="unused")
    stranger = auth.User(id=str(uuid.uuid4()), name="Stranger", email=f"{uuid.uuid4().hex}@example.com", hashed_password="unused")
    for user in (owner, stranger):
        auth._save_user(user)
    assert store.claim_case(case_id, owner.id)
    headers = {"Authorization": f"Bearer {auth._create_token(stranger.id)}"}
    assert client.put(f"/api/records/timekeeping/{entry['id']}", headers=headers, json={**payload, "hours": 2}).status_code == 404
    assert client.delete(f"/api/records/timekeeping/{entry['id']}?case_id={case_id}", headers=headers).status_code == 404
    assert client.post("/api/records/renewals", headers=headers, json={"case_id": case_id, "program": "IHSS"}).status_code == 404
    owner_headers = {"Authorization": f"Bearer {auth._create_token(owner.id)}"}
    reminder = client.post("/api/reminders", headers=owner_headers, json={"case_id": case_id}).json()
    assert client.get(f"/api/reminders/{reminder['id']}", headers=headers).status_code == 404
    assert client.patch(f"/api/reminders/{reminder['id']}", headers=headers, json={"active": False}).status_code == 404
    assert client.delete(f"/api/reminders/{reminder['id']}", headers=headers).status_code == 404


def test_anonymous_reminders_are_listed_only_for_requested_case():
    first, second = case(), case()
    entry = client.post("/api/reminders", json={"case_id": first}).json()
    assert client.get(f"/api/reminders?case_id={first}").json()[0]["id"] == entry["id"]
    assert client.get(f"/api/reminders?case_id={second}").json() == []
    assert client.get("/api/reminders").json() == []
