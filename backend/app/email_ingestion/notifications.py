"""Graph basic notifications: validate metadata, then publish identifiers only.

Never fetch messages here. Invalid notifications are acknowledged without revealing
validation results; infrastructure failures return 503 so Graph retries the batch.
"""

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool

from .. import db
from ..config import get_settings
from .connections import _lock, _write_connection
from .models import EmailScanJob, MailboxConnection
from .queue import ScanPublisher, enqueue_scan
from .privacy import PrivateEmailRoute

router = APIRouter(prefix="/api/email/microsoft", tags=["email"], route_class=PrivateEmailRoute)
MAX_BODY_BYTES = 1024 * 1024


def _matches(mailbox: MailboxConnection, notice: dict) -> bool:
    state = notice.get("clientState")
    return bool(
        mailbox.provider == "microsoft"
        and mailbox.status == "connected"
        and mailbox.subscription_id == notice.get("subscriptionId")
        and mailbox.subscription_expires_at
        and mailbox.subscription_expires_at > datetime.now(timezone.utc)
        and mailbox.tenant_id == notice.get("tenantId")
        and isinstance(state, str) and len(state) <= 128
        and mailbox.subscription_client_state_hash
        and secrets.compare_digest(
            hashlib.sha256(state.encode()).hexdigest(), mailbox.subscription_client_state_hash
        )
    )


def process_notification(notice: dict, publish=None) -> None:
    subscription_id = notice.get("subscriptionId")
    if not isinstance(subscription_id, str) or not subscription_id or len(subscription_id) > 256:
        return
    with db.connection() as conn:
        row = conn.execute(
            "SELECT e.doc FROM email_connections e JOIN cases c ON c.id = e.case_id "
            "WHERE e.doc->>'subscription_id' = %s AND c.owner_user_id = e.doc->>'user_id'",
            (subscription_id,),
        ).fetchone()
        if row is None:
            return
        mailbox = MailboxConnection.model_validate(row[0])
        if not _matches(mailbox, notice):
            return
        # Serialize publishing and lifecycle updates against disconnect/reconnect.
        _lock(conn, mailbox.user_id, mailbox.case_id)
        row = conn.execute(
            "SELECT e.doc FROM email_connections e JOIN cases c ON c.id = e.case_id "
            "WHERE e.id = %s AND c.owner_user_id = e.doc->>'user_id'", (mailbox.id,),
        ).fetchone()
        if row is None:
            return
        mailbox = MailboxConnection.model_validate(row[0])
        if not _matches(mailbox, notice):
            return
        lifecycle = notice.get("lifecycleEvent")
        if lifecycle is not None:
            if lifecycle == "reauthorizationRequired":
                mailbox.subscription_renewal_required = True
            elif lifecycle == "subscriptionRemoved":
                mailbox.subscription_id = None
                mailbox.subscription_expires_at = None
                mailbox.subscription_client_state_hash = None
                mailbox.reconciliation_required = True
            elif lifecycle == "missed":
                mailbox.reconciliation_required = True
            else:
                return
            _write_connection(conn, mailbox)
            return
        data = notice.get("resourceData")
        if notice.get("changeType") != "created" or not isinstance(data, dict):
            return
        message_id = data.get("id")
        if not isinstance(message_id, str) or not 1 <= len(message_id) <= 2048:
            return
        (publish or enqueue_scan)(EmailScanJob(provider="microsoft", connection_id=mailbox.id, message_id=message_id))


def process_batch(notices: list[dict]) -> None:
    # One thread hop and one lazy AMQP connection for the whole request.
    with ScanPublisher() as publisher:
        for notice in notices:
            process_notification(notice, publisher.send)


@router.post("/notifications")
async def notifications(request: Request):
    # Graph validates before returning the subscription ID. No DB/lock/auth needed.
    token = request.query_params.get("validationToken")
    if token is not None:
        if not token or len(token) > 4096:
            raise HTTPException(400, "Invalid validation token")
        return PlainTextResponse(token, headers={"Cache-Control": "no-store"})
    settings = get_settings()
    if not (settings.email_scanning_enabled and settings.has_postgres
            and settings.email_service_bus_namespace):
        raise HTTPException(503, "Email notifications are unavailable")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(413, "Notification batch is too large")
    try:
        import json
        payload = json.loads(body)
        notices = payload["value"]
        if not isinstance(notices, list) or len(notices) > 1000 or any(not isinstance(n, dict) for n in notices):
            raise ValueError
    except (ValueError, KeyError, TypeError, RecursionError):
        raise HTTPException(400, "Invalid notification batch") from None
    try:
        await run_in_threadpool(process_batch, notices)
    except Exception:
        # No provider/queue/DB exception text in responses or logs.
        raise HTTPException(503, "Notification delivery failed; retry later") from None
    return Response(status_code=202)
