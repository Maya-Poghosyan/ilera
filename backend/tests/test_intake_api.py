"""The public intake cannot bypass schema validation or inject a CaseProfile."""
from fastapi.testclient import TestClient

from app import main
from app.routes import cases
from app.intake.logic import answer_context, visible
from app.intake.schema import build_schema


from tests.intake_helpers import complete_current_intake as complete_answers


def test_invalid_or_profile_based_requests_never_persist_or_start(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid intake reached persistence/orchestration")
    monkeypatch.setattr(cases, "save_profile", forbidden)
    monkeypatch.setattr(cases, "_ensure_eligibility_started", forbidden)
    client = TestClient(main.app)
    for body in ({"profile": {"id": "injected"}}, {"answers": {}}, {"answers": {"recipient.household_size": 0}},
                 {"answers": complete_answers(), "profile": {"id": "injected"}}):
        assert client.post("/api/intake", json=body).status_code == 422


def test_complete_intake_is_clean_and_does_not_invent_exact_income(monkeypatch):
    stored = {}
    monkeypatch.setattr(cases, "save_profile", lambda p: stored.update({p.id: p}))
    monkeypatch.setattr(cases, "get_profile", lambda key: stored[key])
    async def start(key):
        return stored[key]
    monkeypatch.setattr(cases, "_ensure_eligibility_started", start)
    answers = complete_answers()
    answers["recipient.program_statuses"] = {"IHSS": "Denied"}  # hidden stale branch
    response = TestClient(main.app).post("/api/intake", json={"answers": answers})
    assert response.status_code == 200, response.text
    result = response.json()
    assert "recipient.program_statuses" not in result["answers"]
    assert "recipient.age" not in result["answers"]
    assert result["household"]["income_monthly"] is None
    assert result["household"]["reported_income_monthly"] is None
    assert result["care_recipient"]["gross_monthly_income"] is None
    assert result["care_recipient"]["state"] == "CA"
