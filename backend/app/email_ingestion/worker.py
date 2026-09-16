"""Standalone peek-lock worker: python -m app.email_ingestion.worker.

Email bodies exist only during processing. Only structured suggestions and a minimal
completion ledger are persisted, atomically. Never print exceptions or broker bodies.
"""

from __future__ import annotations

import asyncio
import signal
import threading
import uuid

from .. import db
from ..config import get_settings
from ..suggested_events import SuggestedEvent
from ..providers.microsoft import ReauthorizationRequired
from . import connections
from .extraction import AzureExtractor, EXTRACTION_VERSION, Extraction, require_extraction_configuration
from .models import EmailScanJob, MailboxConnection, ScanResult
from .privacy import private_transport_logs


class RetryScan(Exception):
    pass


def _active_connection(conn, job: EmailScanJob) -> MailboxConnection | None:
    row = conn.execute(
        "SELECT e.doc FROM email_connections e JOIN cases c ON c.id = e.case_id "
        "WHERE e.id = %s AND c.owner_user_id = e.doc->>'user_id'", (job.connection_id,),
    ).fetchone()
    if row is None:
        return None
    mailbox = MailboxConnection.model_validate(row[0])
    return mailbox if mailbox.status == "connected" and mailbox.provider == job.provider else None


def _commit_result(conn, job: EmailScanJob, original: MailboxConnection, extraction: Extraction) -> str:
    # Same lock as disconnect/reconnect. If either won the race, discard transient output.
    connections._lock(conn, original.user_id, original.case_id)
    current = _active_connection(conn, job)
    if (current is None or current.user_id != original.user_id or current.case_id != original.case_id
            or current.consented_at != original.consented_at):
        return "inactive"
    event_ids = []
    # Preserve first-seen order, but remove repeated identical events within this email.
    seen = set()
    for item in extraction.events:
        fingerprint = item.model_dump_json()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ilera:email:{job.deduplication_id}:{len(event_ids)}"))
        event = SuggestedEvent(
            id=event_id, date=item.date, date_status=item.date_status, timezone=item.timezone,
            title=item.title, time=item.time, kind=item.kind, description=item.explanation,
            source="email", user_id=current.user_id, case_id=current.case_id,
            connection_id=current.id, provider_message_id=job.message_id,
            confidence=item.confidence, action_required=item.action_required,
            model_version=EXTRACTION_VERSION, status="pending",
        )
        conn.execute("INSERT INTO suggested_events (id, doc) VALUES (%s, %s::jsonb)",
                     (event.id, event.model_dump_json()))
        event_ids.append(event.id)
    result = ScanResult(
        id=job.deduplication_id, connection_id=current.id, user_id=current.user_id,
        case_id=current.case_id, provider=job.provider, message_id=job.message_id,
        status="suggested" if event_ids else "no_event", suggested_event_ids=event_ids,
        model_version=EXTRACTION_VERSION,
    )
    conn.execute("INSERT INTO email_scan_results (id, case_id, doc) VALUES (%s, %s, %s::jsonb)",
                 (result.id, result.case_id, result.model_dump_json()))
    return result.status


def process_job(job: EmailScanJob, extractor) -> str:
    if not get_settings().email_scanning_enabled or not db.available():
        raise RetryScan("email_scanning_unavailable")
    if job.provider != "microsoft":
        return "unsupported"
    with db.connection() as conn:
        # Try-lock avoids occupying a pool slot waiting on duplicate model work.
        locked = conn.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))",
                              ("email-job:" + job.deduplication_id,)).fetchone()[0]
        if not locked:
            raise RetryScan("email_scan_busy")
        if conn.execute("SELECT 1 FROM email_scan_results WHERE id = %s", (job.deduplication_id,)).fetchone():
            return "duplicate"
        mailbox = _active_connection(conn, job)
        if mailbox is None:
            return "inactive"
        try:
            token = connections.access_token(connection_id=mailbox.id, user_id=mailbox.user_id)
        except ReauthorizationRequired:
            return "inactive"  # Refresh helper already persisted reconnect state.
        current = _active_connection(conn, job)
        if current is None or current.consented_at != mailbox.consented_at:
            return "inactive"
        try:
            message = asyncio.run(connections._provider().fetch_message(token, job.message_id))
        except ReauthorizationRequired:
            connections._lock(conn, mailbox.user_id, mailbox.case_id)
            current = _active_connection(conn, job)
            if current is not None and current.consented_at == mailbox.consented_at:
                current.status = "reauthorization_required"
                current.reconciliation_required = True
                connections._write_connection(conn, current)
            return "inactive"
        del token
        try:
            if message.message_id != job.message_id:
                raise RetryScan("email_message_mismatch")
            current = _active_connection(conn, job)
            if current is None or current.consented_at != mailbox.consented_at:
                return "inactive"
            extraction = extractor.extract(message)
        finally:
            del message
        # Exiting the DB context commits both suggestions and completion before caller ACKs.
        return _commit_result(conn, job, mailbox, extraction)


def settle_message(receiver, message, extractor) -> str:
    try:
        body = bytearray()
        for part in message.body:
            body.extend(part)
            if len(body) > 8192:
                raise ValueError("oversized job")
        job = EmailScanJob.model_validate_json(bytes(body))
    except Exception:
        # Unknown payloads could contain PHI. Do not copy them into a dead-letter queue.
        receiver.complete_message(message)
        return "invalid_job_discarded"
    finally:
        if 'body' in locals():
            del body
    try:
        outcome = process_job(job, extractor)
    except Exception:
        if message.delivery_count >= get_settings().email_scan_max_deliveries:
            receiver.dead_letter_message(message, reason="email_scan_failed", error_description="Processing failed")
            return "dead_lettered"
        receiver.abandon_message(message)
        return "retry"
    receiver.complete_message(message)
    return outcome


def run_worker() -> None:
    settings = get_settings()
    require_extraction_configuration()
    if not (settings.email_scanning_enabled and settings.has_postgres and settings.email_service_bus_namespace
            and settings.email_connections_enabled and settings.email_key_vault_url
            and settings.email_microsoft_client_id and settings.email_microsoft_tenant_id
            and settings.email_microsoft_redirect_uri and 1 <= settings.email_scan_max_deliveries <= 5):
        raise RuntimeError("email_worker_unconfigured")
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
    from azure.servicebus import AutoLockRenewer, ServiceBusClient, ServiceBusReceiveMode

    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    credential = (ManagedIdentityCredential(client_id=settings.email_managed_identity_client_id or None)
                  if settings.email_use_managed_identity else DefaultAzureCredential())
    with private_transport_logs(), credential, AzureExtractor() as extractor:
        with ServiceBusClient(settings.email_service_bus_namespace, credential=credential,
                              logging_enable=False) as client:
            # One message per worker at a time: no prefetched messages losing locks while
            # waiting for extraction. Replicas provide bounded concurrency.
            with client.get_queue_receiver(settings.email_service_bus_queue,
                    receive_mode=ServiceBusReceiveMode.PEEK_LOCK, prefetch_count=0) as receiver:
                with AutoLockRenewer(max_lock_renewal_duration=180) as renewer:
                    while not stop.is_set():
                        for message in receiver.receive_messages(max_message_count=1, max_wait_time=10):
                            renewer.register(receiver, message, max_lock_renewal_duration=180)
                            outcome = settle_message(receiver, message, extractor)
                            print("email_scan_" + outcome, flush=True)


if __name__ == "__main__":
    try:
        run_worker()
    except Exception:
        print("email_worker_unavailable", flush=True)
        raise SystemExit(1) from None
