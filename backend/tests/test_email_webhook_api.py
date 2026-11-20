"""QA: the public Microsoft Graph webhook, against real stored mailboxes in Postgres.

Only Service Bus (the queue the webhook publishes to) is replaced. Graph cannot be trusted:
every forged, stale or mismatched notice must be acknowledged and dropped silently.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import auth, db, store
from app.config import get_settings
from app.email_ingestion import notifications
from app.email_ingestion.models import MailboxConnection
from app.email_ingestion.store import get_connection, save_connection
from app.models import CaseProfile

URL = "/api/email/microsoft/notifications"
STATE = "client-state-secret"


@pytest.fixture
def queue(monkeypatch):
    monkeypatch.setenv("EMAIL_SERVICE_BUS_NAMESPACE", "ilera-email-bus.servicebus.windows.net")
    get_settings.cache_clear()
    jobs = []

    class Publisher:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def send(self, job):
            jobs.append(job)

    monkeypatch.setattr(notifications, "ScanPublisher", Publisher)
    yield jobs
    get_settings.cache_clear()


def user() -> auth.User:
    account = auth.User(id=str(uuid.uuid4()), name="Owner", email=f"{uuid.uuid4().hex}@example.com",
                        hashed_password="x", created_at="2026-01-01T00:00:00+00:00")
    auth._save_user(account)
    return account


def connected_mailbox(**patch) -> MailboxConnection:
    owner = user()
    case_id = f"case-{uuid.uuid4().hex}"
    store.save_profile(CaseProfile(id=case_id))
    store.claim_case(case_id, owner.id)
    fields = dict(
        id=f"conn-{uuid.uuid4().hex}", user_id=owner.id, case_id=case_id, provider="microsoft",
        provider_account_id="account", credential_id="credential", tenant_id="tenant",
        status="connected", consented_at=datetime.now(timezone.utc),
        subscription_id=f"sub-{uuid.uuid4().hex}",
        subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=2),
        subscription_client_state_hash=hashlib.sha256(STATE.encode()).hexdigest())
    mailbox = MailboxConnection(**{**fields, **patch})
    save_connection(mailbox)
    return mailbox


def notice(mailbox, **patch):
    return {"subscriptionId": mailbox.subscription_id, "tenantId": "tenant", "clientState": STATE,
            "changeType": "created", "resourceData": {"id": "message-1"}, **patch}


def test_subscription_validation_echoes_the_token_as_plain_text(client):
    response = client.post(URL + "?validationToken=abc%20123")
    assert response.status_code == 200
    assert response.text == "abc 123"
    assert response.headers["content-type"].startswith("text/plain")


def test_a_genuine_new_message_queues_only_identifiers(client, queue):
    mailbox = connected_mailbox()
    assert client.post(URL, json={"value": [notice(mailbox)]}).status_code == 202
    assert [(j.connection_id, j.message_id) for j in queue] == [(mailbox.id, "message-1")]


def test_forged_stale_or_mismatched_notices_are_acknowledged_and_dropped(client, queue):
    mailbox = connected_mailbox()
    expired = connected_mailbox(subscription_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    disconnected = connected_mailbox(status="disconnected")
    forged = [
        notice(mailbox, clientState="guessed"),
        notice(mailbox, tenantId="another-tenant"),
        notice(mailbox, subscriptionId="unknown-subscription"),
        notice(mailbox, changeType="updated"),
        notice(mailbox, resourceData={"id": ""}),
        notice(expired),
        notice(disconnected),
    ]
    assert client.post(URL, json={"value": forged}).status_code == 202
    assert queue == []


def test_a_mailbox_whose_case_changed_hands_receives_nothing(client, queue):
    mailbox = connected_mailbox()
    with db.connection() as conn:
        conn.execute("UPDATE cases SET owner_user_id = %s WHERE id = %s", (user().id, mailbox.case_id))
    assert client.post(URL, json={"value": [notice(mailbox)]}).status_code == 202
    assert queue == []


def test_missed_notifications_flag_the_mailbox_for_recovery(client, queue):
    mailbox = connected_mailbox()
    missed = notice(mailbox, lifecycleEvent="missed", changeType=None, resourceData=None)
    assert client.post(URL, json={"value": [missed]}).status_code == 202
    assert queue == []
    assert get_connection(mailbox.id).reconciliation_required is True


def test_bad_batches_are_rejected_and_failures_disclose_nothing(client, queue, monkeypatch):
    assert client.post(URL, content=b"not json").status_code == 400
    assert client.post(URL, json={"value": "nope"}).status_code == 400
    assert client.post(URL, content=b"x" * (notifications.MAX_BODY_BYTES + 1)).status_code == 413

    def broken(*args, **kwargs):
        raise RuntimeError("PHI-SENTINEL internal detail")
    monkeypatch.setattr(notifications, "process_batch", broken)
    response = client.post(URL, json={"value": [notice(connected_mailbox())]})
    assert response.status_code == 503
    assert "PHI-SENTINEL" not in response.text
    assert response.headers["cache-control"] == "no-store"
