"""QA: the public intake endpoint, end to end through validation, mapping and Postgres."""
from app.cases.store import get_profile
from tests.intake_helpers import complete_current_intake


def test_invalid_or_injected_intakes_are_rejected_and_nothing_starts(client, orchestrator):
    for body in ({"profile": {"id": "injected"}}, {"answers": {}}, {"answers": {"recipient.household_size": 0}},
                 {"answers": complete_current_intake(), "profile": {"id": "injected"}}):
        assert client.post("/api/intake", json=body).status_code == 422
    assert orchestrator == []


def test_complete_intake_is_saved_clean_and_readable_by_its_holder(client, orchestrator):
    answers = complete_current_intake()
    answers["recipient.program_statuses"] = {"IHSS": "Denied"}  # hidden, stale branch
    response = client.post("/api/intake", json={"answers": answers})
    assert response.status_code == 200, response.text
    case = response.json()
    assert orchestrator == [case["id"]]
    assert case["eligibility_status"] == "processing"

    stored = get_profile(case["id"])
    assert "recipient.program_statuses" not in stored.answers
    # Reported income stays unknown rather than being invented.
    assert stored.household.income_monthly is None
    assert stored.care_recipient.gross_monthly_income is None
    # Uncertain and declined answers to sensitive questions reach the specialists as such.
    assert stored.answers["caregiver.work_authorized"] == "I'm not sure"
    assert stored.answers["recipient.five_year_us_residence"] == "Prefer not to answer"

    # Before signup the case is unowned: whoever holds the id can read it back.
    assert client.get(f"/api/case/{case['id']}").json()["id"] == case["id"]
