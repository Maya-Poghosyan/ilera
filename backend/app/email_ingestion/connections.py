"""Microsoft connection lifecycle. Called from synchronous FastAPI worker threads.

Case-scoped transaction locks serialize callbacks, refresh, and disconnect, including
across API replicas. Provider calls are bounded; no credential is returned to a browser.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import SecretStr

from .. import db
from ..providers.microsoft import MicrosoftEmailProvider, ProviderError, ReauthorizationRequired
from . import credentials
from .models import MailboxConnection


class ConnectionError(Exception):
    pass


def _lock(conn, user_id: str, case_id: str) -> None:
    # A transaction-scoped database lock, not a process-local lock.
    identity = f"email:{user_id}:{case_id}"
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (identity,))


def _require_owner(conn, user_id: str, case_id: str) -> None:
    row = conn.execute("SELECT 1 FROM cases WHERE id = %s AND owner_user_id = %s",
                       (case_id, user_id)).fetchone()
    if row is None:
        raise ConnectionError("Case not found")


def _provider() -> MicrosoftEmailProvider:
    return MicrosoftEmailProvider(credentials.client_secret())


def _write_connection(conn, mailbox: MailboxConnection) -> None:
    conn.execute(
        "INSERT INTO email_connections (id, case_id, doc) VALUES (%s, %s, %s::jsonb) "
        "ON CONFLICT (id) DO UPDATE SET doc = EXCLUDED.doc, updated_at = now()",
        (mailbox.id, mailbox.case_id, mailbox.model_dump_json()),
    )


def _write_tokens(conn, connection_id: str, envelope: str) -> None:
    conn.execute(
        "INSERT INTO email_credentials (connection_id, encrypted_tokens) VALUES (%s, %s) "
        "ON CONFLICT (connection_id) DO UPDATE SET encrypted_tokens = EXCLUDED.encrypted_tokens, updated_at = now()",
        (connection_id, envelope),
    )


def begin_connection(*, user_id: str, case_id: str) -> str:
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    provider = _provider()
    encrypted = credentials.encrypt({"verifier": verifier, "nonce": nonce})
    with db.connection() as conn:
        _lock(conn, user_id, case_id)
        _require_owner(conn, user_id, case_id)
        conn.execute("DELETE FROM email_oauth_states WHERE expires_at <= now() OR (user_id = %s AND case_id = %s)",
                     (user_id, case_id))
        conn.execute(
            "INSERT INTO email_oauth_states (state_hash, user_id, case_id, encrypted_payload, expires_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (hashlib.sha256(state.encode()).hexdigest(), user_id, case_id, encrypted,
             datetime.now(timezone.utc) + timedelta(minutes=10)),
        )
    return provider.authorize(state=state, code_challenge=challenge, nonce=nonce)


def finish_connection(*, user_id: str, state: str, code: str | None, denied: bool) -> MailboxConnection:
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    failure = None
    mailbox = None
    with db.connection() as conn:
        row = conn.execute("SELECT case_id FROM email_oauth_states WHERE state_hash = %s AND user_id = %s",
                           (state_hash, user_id)).fetchone()
        if row is None:
            raise ConnectionError("Connection request expired or already used")
        case_id = row[0]
        _lock(conn, user_id, case_id)
        _require_owner(conn, user_id, case_id)
        row = conn.execute(
            "DELETE FROM email_oauth_states WHERE state_hash = %s AND user_id = %s AND expires_at > now() "
            "RETURNING encrypted_payload", (state_hash, user_id),
        ).fetchone()
        if row is None:
            raise ConnectionError("Connection request expired or already used")
        # Catch expected failures inside the transaction so consuming state still commits.
        # A savepoint rolls back any partial credential/metadata writes on failure.
        try:
            with conn.transaction():
                if denied or not code:
                    raise ConnectionError("Microsoft connection was cancelled")
                flow = credentials.decrypt(row[0])
                account = asyncio.run(_provider().exchange_code(code=code, code_verifier=flow["verifier"], nonce=flow["nonce"]))
                connection_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                    f"ilera:mailbox:{user_id}:{case_id}:microsoft:{account.tenant_id}:{account.provider_account_id}"))
                existing = conn.execute("SELECT doc FROM email_connections WHERE id = %s", (connection_id,)).fetchone()
                mailbox = MailboxConnection.model_validate(existing[0]) if existing else MailboxConnection(
                    id=connection_id, user_id=user_id, case_id=case_id, provider="microsoft",
                    provider_account_id=account.provider_account_id, tenant_id=account.tenant_id,
                    credential_id=connection_id, consented_at=datetime.now(timezone.utc),
                )
                mailbox.mailbox_address = account.mailbox_address
                mailbox.status = "connected"
                mailbox.consented_at = datetime.now(timezone.utc)
                mailbox.granted_scopes = account.tokens.scopes
                sealed = credentials.seal_tokens(account.tokens)
                _write_connection(conn, mailbox)
                _write_tokens(conn, mailbox.id, sealed)
        except (ConnectionError, ProviderError, credentials.CredentialError) as exc:
            failure = exc
    if failure:
        raise failure
    if mailbox is None:
        raise ConnectionError("Microsoft connection failed")
    return mailbox


def _owned_connection(conn, connection_id: str, user_id: str) -> MailboxConnection:
    row = conn.execute("SELECT doc FROM email_connections WHERE id = %s AND doc->>'user_id' = %s",
                       (connection_id, user_id)).fetchone()
    if row is None:
        raise ConnectionError("Connection not found")
    mailbox = MailboxConnection.model_validate(row[0])
    _require_owner(conn, user_id, mailbox.case_id)
    return mailbox


def access_token(*, connection_id: str, user_id: str) -> SecretStr:
    """Worker-only helper. Serialize refresh-token rotation against disconnect/reconnect."""
    failure = None
    result = None
    with db.connection() as conn:
        mailbox = _owned_connection(conn, connection_id, user_id)
        _lock(conn, user_id, mailbox.case_id)
        mailbox = _owned_connection(conn, connection_id, user_id)
        if mailbox.status != "connected":
            raise ConnectionError("Connection is inactive")
        row = conn.execute("SELECT encrypted_tokens FROM email_credentials WHERE connection_id = %s",
                           (connection_id,)).fetchone()
        if row is None:
            raise ConnectionError("Connection credentials are missing")
        tokens = credentials.open_tokens(row[0])
        try:
            if tokens.expires_at <= datetime.now(timezone.utc) + timedelta(minutes=5):
                tokens = asyncio.run(_provider().refresh_token(tokens.refresh_token))
                _write_tokens(conn, connection_id, credentials.seal_tokens(tokens))
                mailbox.granted_scopes = tokens.scopes
                _write_connection(conn, mailbox)
            result = tokens.access_token
        except ReauthorizationRequired as exc:
            mailbox.status = "reauthorization_required"
            _write_connection(conn, mailbox)
            failure = exc
    if failure:
        raise failure
    if result is None:
        raise ConnectionError("Connection credentials are missing")
    return result


def disconnect(*, connection_id: str, user_id: str) -> bool:
    """Disable locally and delete tokens even if Graph is unavailable.

    Returns whether subscription cleanup remains pending; the subscription ID is retained
    for reconciliation and expires at Microsoft. The future webhook must reject inactive rows.
    """
    with db.connection() as conn:
        mailbox = _owned_connection(conn, connection_id, user_id)
        _lock(conn, user_id, mailbox.case_id)
        mailbox = _owned_connection(conn, connection_id, user_id)
        cleanup_pending = bool(mailbox.subscription_id)
        if mailbox.subscription_id:
            try:
                row = conn.execute("SELECT encrypted_tokens FROM email_credentials WHERE connection_id = %s",
                                   (connection_id,)).fetchone()
                if row:
                    tokens = credentials.open_tokens(row[0])
                    provider = _provider()
                    if tokens.expires_at <= datetime.now(timezone.utc):
                        tokens = asyncio.run(provider.refresh_token(tokens.refresh_token))
                    asyncio.run(provider.unsubscribe(tokens.access_token, mailbox.subscription_id))
                    mailbox.subscription_id = None
                    mailbox.subscription_expires_at = None
                    cleanup_pending = False
            except (ProviderError, credentials.CredentialError):
                pass  # Local deletion must succeed despite an expired grant or provider outage.
        mailbox.status = "disconnected"
        _write_connection(conn, mailbox)
        conn.execute("DELETE FROM email_credentials WHERE connection_id = %s", (connection_id,))
        conn.execute("DELETE FROM email_oauth_states WHERE user_id = %s AND case_id = %s", (user_id, mailbox.case_id))
    return cleanup_pending
