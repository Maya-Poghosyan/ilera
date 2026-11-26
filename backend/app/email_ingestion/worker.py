"""Standalone peek-lock worker: python -m app.email_ingestion.worker.

Email bodies exist only during processing. Only structured suggestions and a minimal
completion ledger are persisted, atomically. Never print exceptions or broker bodies.
"""

from __future__ import annotations

import asyncio
import signal
import threading
import uuid

from app.core import db
from app.core.azure_identity import managed_identity
from app.core.config import get_settings, require_for
from app.calendar.suggestions import SuggestedEvent
from app.calendar.timezones import calendar_timezone
from app.email_ingestion.providers.base import ReauthorizationRequired
from app.email_ingestion import connections
from app.email_ingestion.store import write_connection
from app.email_ingestion.extraction import AzureExtractor, EXTRACTION_VERSION, MIN_SUGGESTION_CONFIDENCE, Extraction
from app.email_ingestion.models import EmailScanJob, MailboxConnection, ScanResult
from app.email_ingestion.privacy import private_transport_logs

MAX_DELIVERIES = 5  # matches the queue's max delivery count; then the message is dead-lettered


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
    connections.lock_mailbox(conn, original.user_id, original.case_id)
    current = _active_connection(conn, job)
    if (current is None or current.user_id != original.user_id or current.case_id != original.case_id
            or current.consented_at != original.consented_at):
        return "inactive"
    event_ids = []
    # A stated time with no zone is in the caregiver's calendar zone (setting, else intake state).
    zone, _source = calendar_timezone(current.case_id)
    # Preserve first-seen order, but remove repeated identical events within this email.
    seen = set()
    for item in extraction.events:
        if item.relevance in {"unrelated", "uncertain"} or item.confidence < MIN_SUGGESTION_CONFIDENCE:
            continue
        fingerprint = item.model_dump_json()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ilera:email:{job.deduplication_id}:{len(event_ids)}"))
        event = SuggestedEvent(
            id=event_id, date=item.date, date_status=item.date_status,
            timezone=item.timezone or (zone if item.time else None),
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
            message = asyncio.run(connections._provider(job.provider).fetch_message(token, job.message_id))
        except ReauthorizationRequired:
            connections.lock_mailbox(conn, mailbox.user_id, mailbox.case_id)
            current = _active_connection(conn, job)
            if current is not None and current.consented_at == mailbox.consented_at:
                current.status = "reauthorization_required"
                current.reconciliation_required = True
                write_connection(conn, current)
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
        if message.delivery_count >= MAX_DELIVERIES:
            receiver.dead_letter_message(message, reason="email_scan_failed", error_description="Processing failed")
            return "dead_lettered"
        receiver.abandon_message(message)
        return "retry"
    receiver.complete_message(message)
    return outcome


def run_worker() -> None:
    settings = get_settings()
    from azure.servicebus import AutoLockRenewer, ServiceBusClient, ServiceBusReceiveMode

    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    credential = managed_identity(settings.email_managed_identity_client_id)
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
    require_for("email-worker")  # names missing settings; safe to print, unlike scan errors
    try:
        run_worker()
    except Exception:
        print("email_worker_unavailable", flush=True)
        raise SystemExit(1) from None
