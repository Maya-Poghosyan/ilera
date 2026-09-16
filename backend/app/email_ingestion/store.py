"""Server-only stores. Live mailbox metadata requires durable Postgres storage."""

from __future__ import annotations

from .. import db
from .models import MailboxConnection, ScanResult

_connections = db.JsonStore("email_connections", scoped_by_case=True)
_results = db.JsonStore("email_scan_results", scoped_by_case=True)


def _require_postgres() -> None:
    if not db.available():
        raise RuntimeError("Email ingestion requires Postgres")


def save_connection(connection: MailboxConnection) -> None:
    _require_postgres()
    _connections.put(connection.id, connection.model_dump_json(), case_id=connection.case_id)


def get_connection(connection_id: str) -> MailboxConnection | None:
    _require_postgres()
    doc = _connections.get(connection_id)
    return MailboxConnection.model_validate(doc) if doc else None


def list_connections(*, user_id: str, case_id: str) -> list[MailboxConnection]:
    _require_postgres()
    return [
        MailboxConnection.model_validate(doc)
        for doc in _connections.list(case_id)
        if doc.get("user_id") == user_id
    ]


def save_scan_result(result: ScanResult) -> None:
    _require_postgres()
    _results.put(result.id, result.model_dump_json(), case_id=result.case_id)


def get_scan_result(job_id: str) -> ScanResult | None:
    _require_postgres()
    doc = _results.get(job_id)
    return ScanResult.model_validate(doc) if doc else None
