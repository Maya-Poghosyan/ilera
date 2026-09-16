"""Missed-notification reconciliation tests.

Boundaries (database, provider, queue) are mocked; these assert the recovery contract:
gap identifiers are enqueued, re-enqueue is deduplicated, the flag/cursor advance only on a
fully covered pass, and inactive/unowned/unflagged connections recover nothing.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.email_ingestion import reconciliation as r
from app.email_ingestion.models import MailboxConnection


@pytest.fixture
def setup(monkeypatch):
    mailbox = MailboxConnection(
        id="connection", user_id="owner", case_id="case", provider="microsoft",
        provider_account_id="account", credential_id="credential", status="connected",
        consented_at=datetime.now(timezone.utc) - timedelta(days=2),
        reconciliation_required=True,
    )
    state = SimpleNamespace(
        mailbox=mailbox, message_ids=["m1", "m2", "m3"], listed_since=[],
        enqueued=[], saved=[], provider_fails=False,
    )

    class Provider:
        async def list_message_ids_since(self, token, *, since, max_ids=500, max_pages=20):
            state.listed_since.append(since)
            if state.provider_fails:
                raise RuntimeError("provider error")
            return list(state.message_ids)

    @contextmanager
    def connection():
        yield object()

    # Publisher stand-in that deduplicates like the real ScanPublisher (by deduplication_id).
    class Publisher:
        def __init__(self):
            self._sent = set()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def send(self, job):
            if job.deduplication_id in self._sent:
                return
            self._sent.add(job.deduplication_id)
            state.enqueued.append(job)

    monkeypatch.setattr(r.db, "connection", connection)
    monkeypatch.setattr(r.connections, "access_token", lambda **kw: SecretStr("token"))
    monkeypatch.setattr(r.connections, "_owned_connection", lambda *a: state.mailbox.model_copy(deep=True))
    monkeypatch.setattr(r.connections, "_lock", lambda *a: None)
    monkeypatch.setattr(r.connections, "_provider", Provider)
    monkeypatch.setattr(r.connections, "_write_connection", lambda conn, mb: state.saved.append(mb))
    monkeypatch.setattr(r, "ScanPublisher", Publisher)
    return state


def test_enqueues_every_gap_identifier_and_clears_flag(setup):
    count = r.reconcile("connection", "owner")
    assert count == 3
    assert [j.message_id for j in setup.enqueued] == ["m1", "m2", "m3"]
    assert all(j.connection_id == "connection" and j.provider == "microsoft" for j in setup.enqueued)
    saved = setup.saved[0]
    assert saved.reconciliation_required is False
    assert saved.reconciled_through is not None


def test_window_starts_at_consented_at_when_never_reconciled(setup):
    r.reconcile("connection", "owner")
    # Window opens at consented_at (minus a small overlap), not "now".
    assert setup.listed_since[0] <= setup.mailbox.consented_at


def test_window_resumes_from_previous_cursor(setup):
    cursor = datetime.now(timezone.utc) - timedelta(hours=1)
    setup.mailbox.reconciled_through = cursor
    r.reconcile("connection", "owner")
    assert setup.listed_since[0] <= cursor
    assert setup.listed_since[0] > setup.mailbox.consented_at


def test_reenqueue_is_deduplicated(setup):
    setup.message_ids = ["m1", "m1", "m2"]
    count = r.reconcile("connection", "owner")
    # Same identifier twice must not produce two jobs.
    assert count == 2
    assert sorted(j.message_id for j in setup.enqueued) == ["m1", "m2"]


def test_provider_failure_leaves_flag_set(setup):
    setup.provider_fails = True
    with pytest.raises(RuntimeError):
        r.reconcile("connection", "owner")
    # Nothing enqueued, nothing written: a later pass retries the whole window.
    assert setup.enqueued == []
    assert setup.saved == []


def test_unflagged_connection_is_a_noop(setup):
    setup.mailbox.reconciliation_required = False
    assert r.reconcile("connection", "owner") == 0
    assert setup.enqueued == [] and setup.saved == []


def test_disconnected_connection_recovers_nothing(setup):
    setup.mailbox.status = "disconnected"
    assert r.reconcile("connection", "owner") == 0
    assert setup.enqueued == [] and setup.saved == []


def test_reconnect_during_listing_discards_pass(setup, monkeypatch):
    # First _owned_connection call (pre-check) sees the flagged mailbox; the post-lock call
    # sees a mailbox whose consent changed — a reconnect raced us, so discard the pass.
    calls = {"n": 0}
    original = setup.mailbox.model_copy(deep=True)
    reconnected = setup.mailbox.model_copy(deep=True)
    reconnected.consented_at = setup.mailbox.consented_at + timedelta(seconds=5)

    def owned(*a):
        calls["n"] += 1
        return original.model_copy(deep=True) if calls["n"] == 1 else reconnected.model_copy(deep=True)

    monkeypatch.setattr(r.connections, "_owned_connection", owned)
    assert r.reconcile("connection", "owner") == 0
    assert setup.saved == []


def test_reconcile_pending_counts_and_isolates_failures(setup, monkeypatch):
    # Two flagged mailboxes: one succeeds, one fails listing. Failure is counted, not raised.
    good = setup.mailbox.model_copy(deep=True)
    bad = setup.mailbox.model_copy(deep=True)
    bad.id = "bad"

    rows = [(good.model_dump(mode="json"),), (bad.model_dump(mode="json"),)]

    @contextmanager
    def connection():
        yield SimpleNamespace(execute=lambda *a, **k: SimpleNamespace(fetchall=lambda: rows))

    monkeypatch.setattr(r.db, "connection", connection)
    monkeypatch.setattr(
        r, "get_settings",
        lambda: SimpleNamespace(email_scanning_enabled=True, email_connections_enabled=True,
                                has_postgres=True, email_service_bus_namespace="bus"),
    )

    def reconcile_one(connection_id, user_id, **kw):
        if connection_id == "bad":
            raise RuntimeError("listing failed")
        return 3

    monkeypatch.setattr(r, "reconcile", reconcile_one)
    result = r.reconcile_pending()
    assert result == {"reconciled": 1, "enqueued": 3, "failed": 1}


def test_reconcile_pending_requires_configuration(monkeypatch):
    monkeypatch.setattr(
        r, "get_settings",
        lambda: SimpleNamespace(email_scanning_enabled=False, email_connections_enabled=True,
                                has_postgres=True, email_service_bus_namespace="bus"),
    )
    with pytest.raises(RuntimeError):
        r.reconcile_pending()


# ---------------------------------------------------------------------------
# Orphan-subscription pruning
# ---------------------------------------------------------------------------

OUR_URL = "https://api.example.test/api/email/microsoft/notifications"


@pytest.fixture
def prune_setup(monkeypatch):
    mailbox = MailboxConnection(
        id="connection", user_id="owner", case_id="case", provider="microsoft",
        provider_account_id="account", credential_id="credential", status="connected",
        consented_at=datetime.now(timezone.utc), subscription_id="live-sub",
        subscription_client_state_hash="a" * 64,
        subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=5),
    )
    state = SimpleNamespace(mailbox=mailbox, subscriptions=[], deleted=[])

    class Provider:
        async def list_subscriptions(self, token, *, max_items=100):
            return list(state.subscriptions)

        async def unsubscribe(self, token, subscription_id):
            state.deleted.append(subscription_id)

    @contextmanager
    def connection():
        yield object()

    monkeypatch.setattr(r.db, "connection", connection)
    monkeypatch.setattr(r.connections, "access_token", lambda **kw: SecretStr("token"))
    monkeypatch.setattr(r.connections, "_owned_connection", lambda *a: state.mailbox.model_copy(deep=True))
    monkeypatch.setattr(r.connections, "_lock", lambda *a: None)
    monkeypatch.setattr(r.connections, "_provider", Provider)
    monkeypatch.setattr(r.connections, "_write_connection", lambda conn, mb: None)
    monkeypatch.setattr(r, "get_settings",
                        lambda: SimpleNamespace(email_microsoft_notification_url=OUR_URL))
    return state


def test_prunes_orphan_pointing_at_our_url(prune_setup):
    prune_setup.subscriptions = [
        {"id": "live-sub", "notification_url": OUR_URL, "resource": "me/messages"},
        {"id": "orphan-1", "notification_url": OUR_URL, "resource": "me/messages"},
    ]
    deleted = r.prune_orphan_subscriptions("connection", "owner")
    assert deleted == 1
    assert prune_setup.deleted == ["orphan-1"]


def test_never_deletes_the_tracked_subscription(prune_setup):
    prune_setup.subscriptions = [{"id": "live-sub", "notification_url": OUR_URL}]
    assert r.prune_orphan_subscriptions("connection", "owner") == 0
    assert prune_setup.deleted == []


def test_leaves_other_integrations_subscriptions_untouched(prune_setup):
    # A subscription delivering somewhere else belongs to another app; never touch it.
    prune_setup.subscriptions = [
        {"id": "foreign", "notification_url": "https://someone-else.example/hook"},
        {"id": "orphan-2", "notification_url": OUR_URL},
    ]
    deleted = r.prune_orphan_subscriptions("connection", "owner")
    assert deleted == 1
    assert prune_setup.deleted == ["orphan-2"]


def test_prune_noop_when_disconnected(prune_setup):
    prune_setup.mailbox.status = "disconnected"
    prune_setup.subscriptions = [{"id": "orphan-3", "notification_url": OUR_URL}]
    assert r.prune_orphan_subscriptions("connection", "owner") == 0
    assert prune_setup.deleted == []


def test_prune_deletes_multiple_orphans(prune_setup):
    prune_setup.subscriptions = [
        {"id": "live-sub", "notification_url": OUR_URL},
        {"id": "orphan-a", "notification_url": OUR_URL},
        {"id": "orphan-b", "notification_url": OUR_URL},
    ]
    assert r.prune_orphan_subscriptions("connection", "owner") == 2
    assert sorted(prune_setup.deleted) == ["orphan-a", "orphan-b"]


def test_prune_ignores_malformed_subscription_entries(prune_setup):
    prune_setup.subscriptions = [
        {"notification_url": OUR_URL},          # no id
        {"id": 123, "notification_url": OUR_URL},  # non-string id
        {"id": "orphan-c", "notification_url": OUR_URL},
    ]
    assert r.prune_orphan_subscriptions("connection", "owner") == 1
    assert prune_setup.deleted == ["orphan-c"]
