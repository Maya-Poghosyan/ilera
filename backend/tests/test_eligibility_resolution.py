"""End-to-end resolution lifecycle without invented resource/policy content."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app
from app.models import CaseProfile
from app.eligibility.facts import write_fact
from app.eligibility.policy import ProgramPolicy
from app.eligibility.resolution import (ResolutionConflict, complete_resolution,
                                       defer_resolution, refresh_resolution)
from app.eligibility.resolution_models import CompletionRequest, ResolutionTemplate
from app.eligibility import routes


def rules(program="one", facts=None):
    facts = facts or ["care_recipient.age"]
    return ProgramPolicy.model_validate({
        "program_id": program, "ruleset_version": "test", "pathways": [{
            "pathway_id": f"{program}.route", "criteria": [{
                "criterion_id": f"{program}.age", "kind": "deterministic", "facts": facts,
                "rule": "care_recipient.age >= 18",
            }]}]})


def request(profile, value=70, key="once"):
    return CompletionRequest(value=value, idempotency_key=key,
                             expected_fact_revision=profile.fact_revision,
                             expected_task_revision=profile.resolution.revision)


def template(status="reviewed"):
    return ResolutionTemplate(
        template_id="age", category="household", profile_path="care_recipient.age", status=status,
        title="Confirm the recipient's age", guided_steps=["Enter their age."],
        resources=[{"resource_id": "sample", "kind": "instructions", "title": "Fixture only",
                    "url": "https://example.test/age", "source_url": "https://example.test/source", "checked_on": "2026-10-12"}],
    )


def test_shared_task_has_all_facts_and_reviewed_guidance():
    original = CaseProfile(id="shared")
    policies = [rules("one", ["care_recipient.age", "care_recipient.state"]), rules("two")]
    profile, evaluations = refresh_resolution(original, policies, [template()])
    assert not original.resolution.tasks
    tasks = list(profile.resolution.tasks.values())
    assert len(tasks) == 2
    age = next(t for t in tasks if t.profile_path == "care_recipient.age")
    assert age.primary_program_id == "one"
    assert age.related_program_ids == ["two"]
    assert age.criterion_ids == ["one.age", "two.age"]
    assert age.template_id == "age" and age.resources[0].resource_id == "sample"
    assert age.category == "household"
    assert "template_version" not in age.model_dump()
    assert "version" not in template().model_dump()
    assert age.input_schema["anyOf"][0]["type"] == "integer"
    assert set(evaluations[0].pathways[0].criteria[0].required_fact_paths) == {"care_recipient.age", "care_recipient.state"}
    same, _ = refresh_resolution(profile, policies, [template()])
    assert same.resolution == profile.resolution


def test_completion_updates_shared_profile_and_both_programs_then_retries():
    policies = [rules("one"), rules("two")]
    profile, _ = refresh_resolution(CaseProfile(id="complete"), policies, [])
    task_id = next(iter(profile.resolution.tasks))
    body = request(profile)
    updated, evaluations = complete_resolution(profile, task_id, body, policies, [])
    assert profile.care_recipient.age is None  # no partial mutation
    assert updated.care_recipient.age == 70
    assert all(e.eligibility_status == "likely_eligible" for e in evaluations)
    assert updated.resolution.tasks[task_id].state == "resolved"
    assert updated.resolution.tasks[task_id].completed_at
    again, _ = complete_resolution(updated, task_id, body, policies, [])
    assert again == updated
    with pytest.raises(ResolutionConflict):
        complete_resolution(updated, task_id, body.model_copy(update={"value": 80}), policies, [])


def test_invalid_and_stale_completion_are_atomic():
    policies = [rules()]
    profile, _ = refresh_resolution(CaseProfile(id="invalid"), policies, [])
    before = profile.model_dump()
    task_id = next(iter(profile.resolution.tasks))
    with pytest.raises(ValueError):
        complete_resolution(profile, task_id, request(profile, "not an age"), policies, [])
    with pytest.raises(ResolutionConflict):
        complete_resolution(profile, task_id, request(profile).model_copy(update={"expected_fact_revision": 999}), policies, [])
    assert profile.model_dump() == before


def test_deferral_survives_refresh_and_correction_reopens_resolved_task():
    policies = [rules()]
    profile, _ = refresh_resolution(CaseProfile(id="defer"), policies, [])
    task_id = next(iter(profile.resolution.tasks))
    profile = defer_resolution(profile, task_id, profile.resolution.revision)
    profile, _ = refresh_resolution(profile, policies, [])
    assert profile.resolution.tasks[task_id].state == "deferred"
    profile, _ = complete_resolution(profile, task_id, request(profile), policies, [])
    completed_at = profile.resolution.tasks[task_id].completed_at
    write_fact(profile, "care_recipient.age", None, availability="conflicting")
    profile, _ = refresh_resolution(profile, policies, [])
    task = profile.resolution.tasks[task_id]
    assert task.state == "available" and task.reopen_reason
    assert task.completed_at == completed_at
    assert task.reasons == ["ambiguous_information"]


def test_agency_criteria_and_eliminated_routes_do_not_create_screening_tasks():
    data = rules().model_dump()
    data["pathways"][0]["criteria"].append({"criterion_id": "county", "kind": "external",
                                            "facts": ["care_recipient.state"], "external_note": "Agency only"})
    policy = ProgramPolicy.model_validate(data)
    profile = CaseProfile(id="external")
    write_fact(profile, "care_recipient.age", 70)
    profile, evaluations = refresh_resolution(profile, [policy], [])
    assert evaluations[0].screening_status == "complete"
    assert not profile.resolution.tasks
    write_fact(profile, "care_recipient.age", 10)
    profile, _ = refresh_resolution(profile, [policy], [])
    assert not profile.resolution.tasks


def test_draft_guidance_and_uploads_are_not_published():
    profile, _ = refresh_resolution(CaseProfile(id="draft"), [rules()], [template("draft")])
    task = next(iter(profile.resolution.tasks.values()))
    assert task.resources == [] and task.template_id is None
    assert task.category == "general"
    assert [m.kind for m in task.methods] == ["manual_entry"]
    with pytest.raises(ValueError):
        ResolutionTemplate.model_validate({**template().model_dump(),
                                           "methods": [{"kind": "document_upload", "label": "Upload"}]})


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
    store.claim_case(case_id, "someone-else")
    assert client.get(base).status_code == 404
    assert client.post(f"{base}/tasks/{task_id}/result", json=body).status_code == 404


@pytest.mark.parametrize("value", ["I'm not sure", "Prefer not to answer", "made up status", ""])
def test_uncertain_or_unsupported_answer_cannot_resolve_task(value):
    policy = ProgramPolicy.model_validate({
        "program_id": "coverage", "ruleset_version": "test", "pathways": [{
            "pathway_id": "coverage.route", "criteria": [{
                "criterion_id": "coverage.status", "kind": "deterministic",
                "facts": ["care_recipient.medicaid_status"],
                "rule": "care_recipient.medicaid_status == 'Enrolled now'"
            }]}]})
    profile, _ = refresh_resolution(CaseProfile(id="unsupported"), [policy], [])
    task_id = next(iter(profile.resolution.tasks))
    with pytest.raises(ValueError):
        complete_resolution(profile, task_id, request(profile, value), [policy], [])
    assert profile.resolution.tasks[task_id].state == "available"
