from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.email_ingestion import subscriptions as s
from app.email_ingestion.models import MailboxConnection
from app.providers.base import EmailSubscription


@pytest.fixture
def setup(monkeypatch):
    mailbox = MailboxConnection(
        id="connection", user_id="owner", case_id="case", provider="microsoft",
        provider_account_id="account", credential_id="credential", status="connected",
        consented_at=datetime.now(timezone.utc),
    )
    state = SimpleNamespace(mailbox=mailbox, created=[], renewed=[], deleted=[], saved=[], fail=False)

    class Provider:
        async def subscribe(self, token, **kwargs):
            state.created.append(kwargs)
            if state.fail:
                raise RuntimeError("provider error")
            return EmailSubscription(id="new-sub", expires_at=datetime.now(timezone.utc) + timedelta(days=6))

        async def renew_subscription(self, token, subscription_id):
            state.renewed.append(subscription_id)
            return EmailSubscription(id=subscription_id, expires_at=datetime.now(timezone.utc) + timedelta(days=6))

        async def unsubscribe(self, token, subscription_id):
            state.deleted.append(subscription_id)

    @contextmanager
    def connection():
        yield object()

    monkeypatch.setattr(s.db, "connection", connection)
    monkeypatch.setattr(s.connections, "access_token", lambda **kw: SecretStr("token"))
    monkeypatch.setattr(s.connections, "_owned_connection", lambda *args: state.mailbox.model_copy(deep=True))
    monkeypatch.setattr(s.connections, "_lock", lambda *args: None)
    monkeypatch.setattr(s.connections, "_provider", Provider)
    monkeypatch.setattr(s.connections, "_write_connection", lambda conn, mailbox: state.saved.append(mailbox))
    state.settings = SimpleNamespace(
        email_scanning_enabled=True, email_connections_enabled=True, has_postgres=True,
        email_service_bus_namespace="bus",
        email_microsoft_notification_url="https://api.example.test/api/email/microsoft/notifications",
    )
    monkeypatch.setattr(s, "get_settings", lambda: state.settings)
    return state


def test_create_stores_only_state_hash_and_marks_gap(setup):
    s.ensure_subscription("connection", "owner")
    assert len(setup.created[0]["client_state"]) >= 32
    saved = setup.saved[0]
    assert saved.subscription_id == "new-sub"
    assert len(saved.subscription_client_state_hash) == 64
    assert setup.created[0]["client_state"] not in saved.model_dump_json()
    assert saved.reconciliation_required


def existing(state, days):
    state.mailbox.subscription_id = "existing"
    state.mailbox.subscription_client_state_hash = "a" * 64
    state.mailbox.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=days)


def test_renew_before_expiry_preserves_state(setup):
    existing(setup, 0.5)
    s.ensure_subscription("connection", "owner")
    assert setup.renewed == ["existing"] and not setup.created
    assert setup.saved[0].subscription_client_state_hash == "a" * 64


def test_no_remote_call_when_not_due(setup, monkeypatch):
    existing(setup, 3)
    monkeypatch.setattr(s.connections, "access_token", lambda **kw: pytest.fail("unnecessary credential access"))
    s.ensure_subscription("connection", "owner")
    assert not setup.renewed and not setup.created and not setup.saved


def test_reauthorization_notice_forces_renewal(setup):
    existing(setup, 3)
    setup.mailbox.subscription_renewal_required = True
    s.ensure_subscription("connection", "owner")
    assert setup.renewed == ["existing"]
    assert not setup.saved[0].subscription_renewal_required


def test_expired_subscription_recreated(setup):
    existing(setup, -1)
    s.ensure_subscription("connection", "owner")
    assert setup.created and not setup.renewed
    assert setup.saved[0].reconciliation_required


def test_disconnect_after_refresh_prevents_creation(setup):
    setup.mailbox.status = "disconnected"
    with pytest.raises(s.connections.ConnectionError):
        s.ensure_subscription("connection", "owner")
    assert not setup.created and not setup.saved


def test_failed_creation_does_not_persist_active_subscription(setup):
    setup.fail = True
    with pytest.raises(RuntimeError):
        s.ensure_subscription("connection", "owner")
    assert not setup.saved


@pytest.mark.parametrize("url", ["http://api.test/api/email/microsoft/notifications",
    "https://user:password@api.test/api/email/microsoft/notifications",
    "https://api.test/api/email/microsoft/notifications?secret=yes", ""])
def test_reject_bad_notification_url(setup, url):
    setup.settings.email_microsoft_notification_url = url
    with pytest.raises(RuntimeError):
        s.ensure_subscription("connection", "owner")
    assert not setup.created


def test_scanning_disabled_blocks_subscriptions(setup):
    setup.settings.email_scanning_enabled = False
    with pytest.raises(RuntimeError):
        s.ensure_subscription("connection", "owner")


def test_maintenance_reconciles_after_ensuring_subscription(setup, monkeypatch):
    # The hourly run both renews/creates subscriptions and recovers any flagged gap.
    rows = [(setup.mailbox.model_dump(mode="json"),)]

    @contextmanager
    def connection():
        yield SimpleNamespace(execute=lambda *a, **k: SimpleNamespace(fetchall=lambda: rows))

    monkeypatch.setattr(s.db, "connection", connection)
    monkeypatch.setattr(s, "ensure_subscription", lambda cid, uid: None)
    calls = []
    monkeypatch.setattr(s, "reconcile", lambda cid, uid: calls.append((cid, uid)) or 4)
    monkeypatch.setattr(s, "prune_orphan_subscriptions", lambda cid, uid: 0)

    result = s.maintain_subscriptions()
    assert calls == [("connection", "owner")]
    assert result["checked"] == 1 and result["reconciled"] == 1 and result["enqueued"] == 4


def test_maintenance_counts_reconciliation_failure_without_stopping(setup, monkeypatch):
    rows = [(setup.mailbox.model_dump(mode="json"),)]

    @contextmanager
    def connection():
        yield SimpleNamespace(execute=lambda *a, **k: SimpleNamespace(fetchall=lambda: rows))

    monkeypatch.setattr(s.db, "connection", connection)
    monkeypatch.setattr(s, "ensure_subscription", lambda cid, uid: None)

    def failing_reconcile(cid, uid):
        raise RuntimeError("gap listing failed")

    monkeypatch.setattr(s, "reconcile", failing_reconcile)
    monkeypatch.setattr(s, "prune_orphan_subscriptions", lambda cid, uid: 0)
    result = s.maintain_subscriptions()
    # Subscription check still counted; reconciliation failure counted separately.
    assert result["checked"] == 1 and result["failed"] == 1 and result["enqueued"] == 0


def test_maintenance_prunes_orphans_and_counts(setup, monkeypatch):
    rows = [(setup.mailbox.model_dump(mode="json"),)]

    @contextmanager
    def connection():
        yield SimpleNamespace(execute=lambda *a, **k: SimpleNamespace(fetchall=lambda: rows))

    monkeypatch.setattr(s.db, "connection", connection)
    monkeypatch.setattr(s, "ensure_subscription", lambda cid, uid: None)
    monkeypatch.setattr(s, "reconcile", lambda cid, uid: 0)
    prune_calls = []
    monkeypatch.setattr(s, "prune_orphan_subscriptions",
                        lambda cid, uid: prune_calls.append((cid, uid)) or 2)

    result = s.maintain_subscriptions()
    assert prune_calls == [("connection", "owner")]
    assert result["pruned"] == 2 and result["failed"] == 0


def test_maintenance_prune_failure_is_isolated(setup, monkeypatch):
    rows = [(setup.mailbox.model_dump(mode="json"),)]

    @contextmanager
    def connection():
        yield SimpleNamespace(execute=lambda *a, **k: SimpleNamespace(fetchall=lambda: rows))

    monkeypatch.setattr(s.db, "connection", connection)
    monkeypatch.setattr(s, "ensure_subscription", lambda cid, uid: None)
    monkeypatch.setattr(s, "reconcile", lambda cid, uid: 1)

    def failing_prune(cid, uid):
        raise RuntimeError("graph list failed")

    monkeypatch.setattr(s, "prune_orphan_subscriptions", failing_prune)
    result = s.maintain_subscriptions()
    # Renew + reconcile still counted; prune failure counted, not raised.
    assert result["checked"] == 1 and result["reconciled"] == 1
    assert result["enqueued"] == 1 and result["failed"] == 1
