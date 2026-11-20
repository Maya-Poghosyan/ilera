"""QA: a caregiver turns an eligible program into filled government forms."""
from tests.factories import auth_headers, new_user
from tests.intake_helpers import complete_current_intake


def test_an_application_asks_only_what_intake_missed_and_returns_filled_forms(client):
    case_id = client.post("/api/intake", json={"answers": complete_current_intake()}).json()["id"]
    base = f"/api/applications/{case_id}/IHSS"

    started = client.post(f"{base}/start")
    assert started.status_code == 200, started.text
    questions = started.json()["questions"]
    assert questions, "IHSS forms ask for facts intake does not collect"
    asked = [q["field_id"] for q in questions]
    assert len(asked) == len(set(asked)), "the same fact is never asked twice"

    answers = {q["field_id"]: (q["options"][0] if q["options"] else "Test") for q in questions}
    pdf = client.post(f"{base}/preview", json={"answers": answers})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.post(f"{base}/complete").json()["status"] == "completed"


def test_another_account_cannot_open_a_claimed_case_s_application(client):
    case_id = client.post("/api/intake", json={"answers": complete_current_intake()}).json()["id"]
    owner = new_user("Owner")
    assert client.patch("/api/auth/me", headers=auth_headers(owner), json={"case_id": case_id}).status_code == 200
    stranger = auth_headers(new_user("Stranger"))
    assert client.post(f"/api/applications/{case_id}/IHSS/start", headers=stranger).status_code == 404
    assert client.post(f"/api/applications/{case_id}/IHSS/start", headers=auth_headers(owner)).status_code == 200
