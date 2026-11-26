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


def test_application_progress_preserves_saved_answers_and_checklists(client):
    from app.cases.models import EligibilityResult
    from app.cases.store import get_profile, save_profile

    case_id = client.post("/api/intake", json={"answers": complete_current_intake()}).json()["id"]
    profile = get_profile(case_id)
    profile.eligibility["ihss"] = EligibilityResult(
        program="IHSS", status="likely", required_documents=["Photo ID"], next_steps=["Submit the packet"]
    )
    profile.eligibility["medical"] = EligibilityResult(program="Medi-Cal", status="likely")
    profile.care_recipient.medicaid_status = "Enrolled now"
    save_profile(profile)
    base = f"/api/applications/{case_id}/IHSS"

    def current_application():
        apps = client.get(f"/api/applications/{case_id}").json()["applications"]
        assert [app["program"] for app in apps] == ["IHSS"]
        return apps[0]

    assert current_application()["form_ids"] == ["soc-295", "soc-426a"]
    assert current_application()["stage"] == "update_information"
    question = client.post(f"{base}/start").json()["questions"][0]
    answer = question["options"][0] if question["options"] else "Test"
    assert client.put(f"{base}/progress", json={
        "stage": "gather_documents", "answers": {question["field_id"]: answer}
    }).status_code == 200
    assert client.post(f"{base}/preview", json={"answers": {}}).content.startswith(b"%PDF")
    assert client.put(f"{base}/progress", json={
        "stage": "review_forms", "ready_documents": ["Photo ID", "Photo ID"]
    }).status_code == 200
    assert client.put(f"{base}/progress", json={
        "stage": "follow_up", "completed_follow_ups": ["Submit the packet"]
    }).status_code == 200

    resumed = current_application()
    assert resumed["stage"] == "follow_up"
    assert resumed["ready_documents"] == ["Photo ID"]
    assert resumed["completed_follow_ups"] == ["Submit the packet"]


def test_approval_links_existing_record_and_does_not_duplicate_on_retry(client):
    case_id = client.post("/api/intake", json={"answers": complete_current_intake()}).json()["id"]
    records = f"/api/records/renewals/{case_id}"
    existing = client.post("/api/records/renewals", json={
        "case_id": case_id, "program": "IHSS", "due_date": "2027-11-02", "notes": "County contact saved",
    }).json()
    application = f"/api/applications/{case_id}/IHSS"
    assert client.patch(application, json={"status": "pending_determination"}).status_code == 200
    request = {"status": "accepted", "approval": {
        "approval_date": "2026-11-01", "effective_date": "2026-11-05", "due_date": "2027-11-10",
    }}
    for _ in range(2):
        accepted = client.patch(application, json=request)
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["renewal_record_id"] == existing["id"]

    [record] = client.get(records).json()
    assert record["source_application"] == "IHSS"
    assert record["approval_date"] == "2026-11-01"
    assert record["effective_date"] == "2026-11-05"
    assert record["due_date"] == "2027-11-02"
    assert record["last_completed_date"] is None
    assert record["notes"] == "County contact saved"


def test_denied_decision_remains_listed_after_eligibility_changes(client):
    case_id = client.post("/api/intake", json={"answers": complete_current_intake()}).json()["id"]
    base = f"/api/applications/{case_id}"
    application = f"{base}/Medicare"
    assert client.patch(application, json={"status": "pending_determination"}).status_code == 200
    assert client.patch(application, json={"status": "denied"}).json()["status"] == "denied"
    [entry] = client.get(base).json()["applications"]
    assert (entry["program"], entry["determination"]) == ("Medicare", "denied")
    assert client.get(f"/api/records/renewals/{case_id}").json() == []
