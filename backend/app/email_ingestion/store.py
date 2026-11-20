"""Server-only stores. Live mailbox metadata requires durable Postgres storage."""

from __future__ import annotations

from app.core import db
from app.email_ingestion.models import MailboxConnection, ScanResult

_connections = db.JsonStore("email_connections", scoped_by_case=True)
_results = db.JsonStore("email_scan_results", scoped_by_case=True)


def write_connection(conn, mailbox: MailboxConnection) -> None:
    """Persist inside the caller's transaction, re-validating first: fields are assigned one
    at a time, so this is where an inconsistent connection is refused."""
    mailbox = MailboxConnection.model_validate(mailbox.model_dump())
    conn.execute(
        "INSERT INTO email_connections (id, case_id, doc) VALUES (%s, %s, %s::jsonb) "
        "ON CONFLICT (id) DO UPDATE SET doc = EXCLUDED.doc, updated_at = now()",
        (mailbox.id, mailbox.case_id, mailbox.model_dump_json()),
    )


def save_connection(mailbox: MailboxConnection) -> None:
    with db.connection() as conn:
        write_connection(conn, mailbox)


def get_connection(connection_id: str) -> MailboxConnection | None:
    doc = _connections.get(connection_id)
    return MailboxConnection.model_validate(doc) if doc else None


def list_connections(*, user_id: str, case_id: str) -> list[MailboxConnection]:
    return [
        MailboxConnection.model_validate(doc)
        for doc in _connections.list(case_id)
        if doc.get("user_id") == user_id
    ]


def save_scan_result(result: ScanResult) -> None:
    _results.put(result.id, result.model_dump_json(), case_id=result.case_id)


def get_scan_result(job_id: str) -> ScanResult | None:
    doc = _results.get(job_id)
    return ScanResult.model_validate(doc) if doc else None
