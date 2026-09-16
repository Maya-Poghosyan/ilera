"""Missed-notification reconciliation: recover messages that arrived while a mailbox had no
working subscription.

A Graph subscription can lapse (expiry, replacement, `subscriptionRemoved`/`missed` lifecycle
events, reconnect). Messages delivered during that gap produce no webhook, so they would never
be scanned. When any of those events occurs the connection is flagged `reconciliation_required`
(see subscriptions.py and notifications.py); nothing clears it until this module proves the gap
is covered.

`reconcile()` lists the identifiers of messages received since the last covered instant and
enqueues an identifier-only scan job for each. Re-enqueueing is safe: the worker deduplicates by
deterministic message identity and writes a single completion ledger per message, so a message
that also arrived via a live webhook is not scanned twice. The flag is cleared and the cursor
advanced only when the whole window was enqueued without error; a partial pass leaves the flag
set so a later run retries. All state changes happen under the same case advisory lock used by
OAuth/disconnect/renewal, so reconciliation can never revive a disconnected mailbox.

Orphan-subscription pruning (`prune_orphan_subscriptions`) handles the inverse leak: a Graph
create that succeeds before the database commit fails leaves a live subscription that no
connection tracks. Such a subscription keeps delivering notifications the webhook cannot match
(they are dropped) until it expires. Pruning lists the mailbox's Graph subscriptions and deletes
any that point at *our* notification URL yet are not the connection's currently tracked
subscription — never touching subscriptions owned by other integrations in the tenant, and never
the live one. It runs under the case lock and re-reads the tracked id after locking so it cannot
race a concurrent create.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from .. import db
from ..config import get_settings
from . import connections
from .models import EmailScanJob, MailboxConnection
from .queue import ScanPublisher

# Overlap the previous cursor slightly so a message received in the same second as the last
# covered instant is never skipped. Idempotent enqueue makes the small re-scan harmless.
_CURSOR_OVERLAP = timedelta(seconds=1)


def _window_start(mailbox: MailboxConnection) -> datetime:
    start = mailbox.reconciled_through or mailbox.consented_at
    return start - _CURSOR_OVERLAP


def reconcile(connection_id: str, user_id: str, *, publish=None) -> int:
    """Enqueue scan jobs for gap messages on one owned, connected mailbox.

    Returns the number of identifiers enqueued this pass. Raises on provider/queue failure so
    the caller counts it as failed and the flag remains set. Does nothing (returns 0) when the
    connection is not flagged, not connected, not owned, or not Microsoft.
    """
    # Cheap pre-check without decrypting credentials or hitting Graph.
    with db.connection() as conn:
        mailbox = connections._owned_connection(conn, connection_id, user_id)
        if not (mailbox.reconciliation_required and mailbox.status == "connected"
                and mailbox.provider == "microsoft"):
            return 0

    # Refresh/fetch the token outside the transaction lock (refresh takes the lock itself).
    token = connections.access_token(connection_id=connection_id, user_id=user_id)
    now = datetime.now(timezone.utc)
    provider = connections._provider()
    message_ids = asyncio.run(provider.list_message_ids_since(token, since=_window_start(mailbox)))
    del token

    enqueued = 0
    with db.connection() as conn:
        connections._lock(conn, user_id, mailbox.case_id)
        current = connections._owned_connection(conn, connection_id, user_id)
        # Re-check under the lock: disconnect/reconnect during listing invalidates this pass.
        if (not current.reconciliation_required or current.status != "connected"
                or current.provider != "microsoft" or current.consented_at != mailbox.consented_at):
            return 0
        if publish is not None:
            enqueued = _enqueue_all(publish, connection_id, message_ids)
        else:
            with ScanPublisher() as publisher:
                enqueued = _enqueue_all(publisher.send, connection_id, message_ids)
        # Only reached if every enqueue above succeeded (a raise propagates out, flag intact).
        current.reconciled_through = now
        current.reconciliation_required = False
        connections._write_connection(conn, current)
    return enqueued


def _enqueue_all(send, connection_id: str, message_ids: list[str]) -> int:
    count = 0
    seen: set[str] = set()
    for message_id in message_ids:
        # A message id repeated within one gap window is the same message; enqueue once.
        if message_id in seen:
            continue
        seen.add(message_id)
        send(EmailScanJob(provider="microsoft", connection_id=connection_id, message_id=message_id))
        count += 1
    return count


def prune_orphan_subscriptions(connection_id: str, user_id: str) -> int:
    """Delete Graph subscriptions for this mailbox that point at our notification URL but are
    not the connection's currently tracked subscription.

    Returns the number deleted. Raises on provider failure so the caller counts it as failed.
    Safe by construction: only subscriptions whose ``notification_url`` exactly matches our
    configured URL are eligible (leaving other integrations' subscriptions untouched), and the
    tracked ``subscription_id`` — re-read under the case lock — is always preserved.
    """
    with db.connection() as conn:
        mailbox = connections._owned_connection(conn, connection_id, user_id)
        if mailbox.status != "connected" or mailbox.provider != "microsoft":
            return 0

    our_url = get_settings().email_microsoft_notification_url
    token = connections.access_token(connection_id=connection_id, user_id=user_id)
    provider = connections._provider()
    subscriptions = asyncio.run(provider.list_subscriptions(token))

    deleted = 0
    with db.connection() as conn:
        connections._lock(conn, user_id, mailbox.case_id)
        current = connections._owned_connection(conn, connection_id, user_id)
        # A concurrent create/renew may have changed the tracked id; honor the latest.
        if current.status != "connected" or current.provider != "microsoft":
            return 0
        tracked = current.subscription_id
        for sub in subscriptions:
            sub_id = sub.get("id")
            if not isinstance(sub_id, str) or sub_id == tracked:
                continue
            # Only prune subscriptions we own: those delivering to our exact notification URL.
            if sub.get("notification_url") != our_url:
                continue
            asyncio.run(provider.unsubscribe(token, sub_id))
            deleted += 1
    del token
    return deleted


def reconcile_pending() -> dict[str, int]:
    """Reconcile every flagged, connected, owned Microsoft mailbox. Fixed counters only."""
    settings = get_settings()
    if not (settings.email_scanning_enabled and settings.email_connections_enabled
            and settings.has_postgres and settings.email_service_bus_namespace):
        raise RuntimeError("Email reconciliation is not configured")
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT e.doc FROM email_connections e JOIN cases c ON c.id = e.case_id "
            "WHERE e.doc->>'provider' = 'microsoft' AND e.doc->>'status' = 'connected' "
            "AND (e.doc->>'reconciliation_required')::boolean IS TRUE "
            "AND c.owner_user_id = e.doc->>'user_id'"
        ).fetchall()
    counts = {"reconciled": 0, "enqueued": 0, "failed": 0}
    for row in rows:
        try:
            mailbox = MailboxConnection.model_validate(row[0])
            counts["enqueued"] += reconcile(mailbox.id, mailbox.user_id)
            counts["reconciled"] += 1
        except Exception:
            counts["failed"] += 1
    return counts


if __name__ == "__main__":
    try:
        result = reconcile_pending()
    except Exception:
        print("email_reconciliation_unavailable")
        raise SystemExit(1) from None
    print(f"reconciled={result['reconciled']} enqueued={result['enqueued']} failed={result['failed']}")
    raise SystemExit(1 if result["failed"] else 0)
