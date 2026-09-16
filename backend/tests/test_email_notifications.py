"""Trust boundary and provider retry behavior, with no Azure credentials needed."""

import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.email_ingestion import notifications as n
from app.email_ingestion.models import EmailScanJob, MailboxConnection


@pytest.fixture
def setup(monkeypatch):
    mailbox = MailboxConnection(
        id="connection", user_id="owner", case_id="case", provider="microsoft",
        provider_account_id="account", credential_id="credential", tenant_id="tenant",
        status="connected", consented_at=datetime.now(timezone.utc),
        subscription_id="subscription", subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=2),
        subscription_client_state_hash=hashlib.sha256(b"secret-state").hexdigest(),
    )
    state = SimpleNamespace(mailbox=mailbox, jobs=[], saved=[], queries=[], missing=False, after_lock=None)

    class Conn:
        def execute(self, sql, params):
            state.queries.append(sql)
            return self

        def fetchone(self):
            return None if state.missing else (state.mailbox.model_dump(mode="json"),)

    @contextmanager
    def connection():
        yield Conn()

    def lock(*args):
        if state.after_lock:
            state.after_lock()

    monkeypatch.setattr(n.db, "connection", connection)
    monkeypatch.setattr(n, "_lock", lock)
    monkeypatch.setattr(n, "_write_connection", lambda conn, m: state.saved.append(m))
    monkeypatch.setattr(n, "enqueue_scan", state.jobs.append)
    class Publisher:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def send(self, job):
            n.enqueue_scan(job)
    monkeypatch.setattr(n, "ScanPublisher", Publisher)
    monkeypatch.setattr(n, "get_settings", lambda: SimpleNamespace(
        email_scanning_enabled=True, has_postgres=True, email_service_bus_namespace="bus"))
    app = FastAPI()
    app.include_router(n.router)
    state.client = TestClient(app)
    return state


def notice(**overrides):
    return {"subscriptionId": "subscription", "tenantId": "tenant", "clientState": "secret-state",
            "changeType": "created", "resourceData": {"id": "immutable-message"}, **overrides}


def send(state, notices):
    return state.client.post("/api/email/microsoft/notifications", json={"value": notices})


def test_challenge_is_plain_text_without_configuration(setup, monkeypatch):
    monkeypatch.setattr(n, "get_settings", lambda: (_ for _ in ()).throw(AssertionError()))
    response = setup.client.post("/api/email/microsoft/notifications", params={"validationToken": "a+b <token>"})
    assert response.status_code == 200
    assert response.text == "a+b <token>"
    assert response.headers["content-type"].startswith("text/plain")
    assert not setup.queries


def test_valid_batch_contains_only_identifiers(setup):
    response = send(setup, [notice(), notice(resourceData={"id": "second", "subject": "ignore"})])
    assert response.status_code == 202
    assert [j.message_id for j in setup.jobs] == ["immutable-message", "second"]
    assert set(setup.jobs[0].model_dump()) == {"version", "provider", "connection_id", "message_id"}
    assert all("c.owner_user_id = e.doc->>'user_id'" in q for q in setup.queries)


@pytest.mark.parametrize("change", [
    {"clientState": "forged"}, {"clientState": None}, {"tenantId": "other"},
    {"subscriptionId": "other"}, {"resourceData": {}}, {"resourceData": {"id": 1}},
    {"changeType": "updated"}, {"lifecycleEvent": "unknown"},
])
def test_forged_or_invalid_notices_enqueue_nothing(setup, change):
    assert send(setup, [notice(**change)]).status_code == 202
    assert not setup.jobs and not setup.saved


@pytest.mark.parametrize("status", ["disconnected", "reauthorization_required", "pending"])
def test_inactive_mailbox(setup, status):
    setup.mailbox.status = status
    assert send(setup, [notice()]).status_code == 202
    assert not setup.jobs


def test_expired_subscription(setup):
    setup.mailbox.subscription_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert send(setup, [notice()]).status_code == 202
    assert not setup.jobs


def test_missing_or_unowned_connection(setup):
    setup.missing = True
    assert send(setup, [notice()]).status_code == 202
    assert not setup.jobs


def test_disconnect_while_waiting_for_lock(setup):
    setup.after_lock = lambda: setattr(setup.mailbox, "status", "disconnected")
    assert send(setup, [notice()]).status_code == 202
    assert not setup.jobs


def test_partial_queue_failure_retries_with_stable_ids(setup, monkeypatch):
    def publish(job):
        if setup.jobs:
            raise RuntimeError("sensitive provider response")
        setup.jobs.append(job)
    monkeypatch.setattr(n, "enqueue_scan", publish)
    response = send(setup, [notice(), notice(resourceData={"id": "second"})])
    assert response.status_code == 503
    assert "sensitive" not in response.text
    first_id = setup.jobs[0].deduplication_id
    setup.jobs.clear()
    monkeypatch.setattr(n, "enqueue_scan", setup.jobs.append)
    assert send(setup, [notice()]).status_code == 202
    assert setup.jobs[0].deduplication_id == first_id


@pytest.mark.parametrize("event", ["missed", "subscriptionRemoved", "reauthorizationRequired"])
def test_lifecycle_is_persisted_without_email_fetch(setup, event):
    assert send(setup, [notice(lifecycleEvent=event)]).status_code == 202
    saved = setup.saved[0]
    assert not setup.jobs
    if event == "reauthorizationRequired":
        assert saved.subscription_renewal_required
    else:
        assert saved.reconciliation_required
    if event == "subscriptionRemoved":
        assert saved.subscription_id is None and saved.subscription_client_state_hash is None


@pytest.mark.parametrize("payload", [None, [], {}, {"value": {}}, {"value": [None]}])
def test_malformed_batch(setup, payload):
    assert setup.client.post("/api/email/microsoft/notifications", json=payload).status_code == 400
    assert not setup.jobs


def test_oversized_body(setup):
    assert setup.client.post("/api/email/microsoft/notifications", content=b"x" * (n.MAX_BODY_BYTES + 1)).status_code == 413


def test_queue_contract_rejects_content():
    with pytest.raises(ValueError):
        EmailScanJob(provider="microsoft", connection_id="c", message_id="m", body="private")
