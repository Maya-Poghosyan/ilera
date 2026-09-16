"""Subscription maintenance entry point: python -m app.email_ingestion.subscriptions.

Run periodically (at least hourly) once the scanning pipeline is deployed. The same
case lock used by OAuth/disconnect prevents stale maintenance from reviving a mailbox.
Only fixed counters are printed; provider errors never reach logs.
"""

import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from .. import db
from ..config import get_settings
from . import connections
from .models import MailboxConnection


def require_configuration() -> None:
    s = get_settings()
    url = urlparse(s.email_microsoft_notification_url)
    if not (s.email_scanning_enabled and s.email_connections_enabled and s.has_postgres
            and s.email_service_bus_namespace and url.scheme == "https" and url.hostname
            and not url.username and not url.password and not url.query and not url.fragment
            and url.path == "/api/email/microsoft/notifications"):
        raise RuntimeError("Email subscription maintenance is not configured")


def ensure_subscription(connection_id: str, user_id: str) -> None:
    require_configuration()
    # Most hourly visits need no credential decryption, vault reads, or Graph calls.
    with db.connection() as conn:
        mailbox = connections._owned_connection(conn, connection_id, user_id)
        if (mailbox.status == "connected" and mailbox.subscription_id
                and mailbox.subscription_client_state_hash and mailbox.subscription_expires_at
                and mailbox.subscription_expires_at > datetime.now(timezone.utc) + timedelta(days=1)
                and not mailbox.subscription_renewal_required):
            return
    # Refresh before acquiring the maintenance transaction lock (refresh takes it too).
    token = connections.access_token(connection_id=connection_id, user_id=user_id)
    with db.connection() as conn:
        mailbox = connections._owned_connection(conn, connection_id, user_id)
        connections._lock(conn, user_id, mailbox.case_id)
        mailbox = connections._owned_connection(conn, connection_id, user_id)
        if mailbox.status != "connected" or mailbox.provider != "microsoft":
            raise connections.ConnectionError("Connection is inactive")
        now = datetime.now(timezone.utc)
        valid = (mailbox.subscription_id and mailbox.subscription_expires_at
                 and mailbox.subscription_expires_at > now and mailbox.subscription_client_state_hash)
        if valid and mailbox.subscription_expires_at > now + timedelta(days=1) and not mailbox.subscription_renewal_required:
            return
        provider = connections._provider()
        if valid:
            subscription = asyncio.run(provider.renew_subscription(token, mailbox.subscription_id))
        else:
            # Clear legacy subscriptions without a verifiable clientState before recreating.
            if mailbox.subscription_id and mailbox.subscription_expires_at and mailbox.subscription_expires_at > now:
                asyncio.run(provider.unsubscribe(token, mailbox.subscription_id))
            state = secrets.token_urlsafe(32)
            subscription = asyncio.run(provider.subscribe(
                token, notification_url=get_settings().email_microsoft_notification_url, client_state=state,
            ))
            mailbox.subscription_client_state_hash = hashlib.sha256(state.encode()).hexdigest()
            # The recovery worker must reconcile the initial/gap interval; never claim it is covered.
            mailbox.reconciliation_required = True
        mailbox.subscription_id = subscription.id
        mailbox.subscription_expires_at = subscription.expires_at
        mailbox.subscription_renewal_required = False
        connections._write_connection(conn, mailbox)


def maintain_subscriptions() -> dict[str, int]:
    require_configuration()
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT e.doc FROM email_connections e JOIN cases c ON c.id = e.case_id "
            "WHERE e.doc->>'provider' = 'microsoft' AND e.doc->>'status' = 'connected' "
            "AND c.owner_user_id = e.doc->>'user_id'"
        ).fetchall()
    counts = {"checked": 0, "failed": 0}
    for row in rows:
        try:
            mailbox = MailboxConnection.model_validate(row[0])
            ensure_subscription(mailbox.id, mailbox.user_id)
            counts["checked"] += 1
        except Exception:
            counts["failed"] += 1
    return counts


if __name__ == "__main__":
    try:
        result = maintain_subscriptions()
    except Exception:
        print("email_subscription_maintenance_unavailable")
        raise SystemExit(1) from None
    print(f"checked={result['checked']} failed={result['failed']}")
    raise SystemExit(1 if result["failed"] else 0)
