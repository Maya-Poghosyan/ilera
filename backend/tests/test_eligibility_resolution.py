"""QA: the eligibility-resolution API — tasks, validation, idempotency, conflicts, ownership."""
import uuid

from fastapi.testclient import TestClient

from app import store
from app.main import app
from app.models import CaseProfile
from app.eligibility.policy import ProgramPolicy
from app.eligibility import routes


def rules(program="one", facts=None):
    facts = facts or ["care_recipient.age"]
    return ProgramPolicy.model_validate({
        "program_id": program, "ruleset_version": "test", "pathways": [{
            "pathway_id": f"{program}.route", "criteria": [{
                "criterion_id": f"{program}.age", "kind": "deterministic", "facts": facts,
                "rule": "care_recipient.age >= 18",
            }]}]})


def test_api_roundtrip_authorization_validation_and_persistence(monkeypatch):
    monkeypatch.setattr(routes, "list_policies", lambda: [rules()])
    monkeypatch.setattr(routes, "load_templates", lambda: [])
    client = TestClient(app)
    case_id = str(uuid.uuid4())
    store.save_profile(CaseProfile(id=case_id))
    base = f"/api/eligibility-resolution/{case_id}"
    response = client.get(base)
    assert response.status_code == 200
    data = response.json()
    assert data["policy_coverage"] == ["one"]
    task_id = data["tasks"][0]["id"]
    assert client.get(base + "?program_id=other").json()["tasks"] == []
    body = {"idempotency_key": "api-once", "expected_fact_revision": data["fact_revision"],
            "expected_task_revision": data["task_revision"], "value": 70}
    invalid = client.post(f"{base}/tasks/{task_id}/result", json={**body, "value": "private-invalid-value"})
    assert invalid.status_code == 422 and "private-invalid-value" not in invalid.text
    result = client.post(f"{base}/tasks/{task_id}/result", json=body)
    assert result.status_code == 200
    assert result.json()["tasks"][0]["state"] == "resolved"
    assert store.get_profile(case_id).care_recipient.age == 70
    assert client.post(f"{base}/tasks/{task_id}/result", json=body).status_code == 200
    assert client.post(f"{base}/tasks/{task_id}/result", json={**body, "value": 80}).status_code == 409
    assert client.get("/api/eligibility-resolution/missing").status_code == 404
    from app import auth
    stranger = auth.User(id=f"stranger-{case_id}", name="S", email=f"{case_id}@example.com",
                         hashed_password="x", created_at="2026-01-01T00:00:00+00:00")
    auth._save_user(stranger)
    store.claim_case(case_id, stranger.id)
    assert client.get(base).status_code == 404
    assert client.post(f"{base}/tasks/{task_id}/result", json=body).status_code == 404
