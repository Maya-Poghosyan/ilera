"""Authenticated mailbox connection endpoints; notifications have a separate trust boundary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, SecretStr

from .. import db
from ..auth import User, get_current_user
from ..config import get_settings
from ..store import get_case_owner
from ..providers.microsoft import ProviderError
from . import connections, credentials
from .models import MailboxConnection
from .store import list_connections

router = APIRouter(prefix="/api/email", tags=["email"])


def _configured() -> bool:
    s = get_settings()
    return bool(s.email_connections_enabled and s.has_postgres and s.email_key_vault_url
                and s.email_microsoft_tenant_id and s.email_microsoft_client_id
                and s.email_microsoft_redirect_uri and s.email_microsoft_client_secret_name
                and s.email_token_encryption_key_name)


def _require_connections() -> None:
    if not _configured():
        raise HTTPException(503, "Microsoft mailbox connections are not available yet")


def _owner(case_id: str, user: User) -> None:
    if get_case_owner(case_id) != user.id:
        raise HTTPException(404, "Case not found")


class PublicConnection(BaseModel):
    id: str
    case_id: str
    provider: str
    status: str
    mailbox_address: str | None = None
    consented_at: str
    # Authorization alone does not mean the ingestion pipeline is running.
    scanning_active: bool = False

    @classmethod
    def from_mailbox(cls, mailbox: MailboxConnection) -> PublicConnection:
        return cls(id=mailbox.id, case_id=mailbox.case_id, provider=mailbox.provider,
                   status=mailbox.status, mailbox_address=mailbox.mailbox_address,
                   consented_at=mailbox.consented_at.isoformat())


@router.get("/providers")
def providers(response: Response, user: User = Depends(get_current_user)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return {"microsoft": {"available": _configured(), "account_type": "organization"},
            "google": {"available": False}}


@router.get("/connections", response_model=list[PublicConnection])
def read_connections(case_id: str, response: Response, user: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    _owner(case_id, user)
    if not db.available():
        return []
    return [PublicConnection.from_mailbox(m) for m in list_connections(user_id=user.id, case_id=case_id)]


class ConnectRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=128)


@router.post("/microsoft/connect")
def connect(body: ConnectRequest, response: Response, user: User = Depends(get_current_user)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    _require_connections()
    _owner(body.case_id, user)
    try:
        return {"authorization_url": connections.begin_connection(user_id=user.id, case_id=body.case_id)}
    except connections.ConnectionError:
        raise HTTPException(404, "Case not found") from None
    except (ProviderError, credentials.CredentialError):
        raise HTTPException(503, "Microsoft mailbox connections are temporarily unavailable") from None


class CallbackRequest(BaseModel):
    state: SecretStr
    code: SecretStr | None = None
    denied: bool = False


@router.post("/microsoft/callback", response_model=PublicConnection)
def callback(body: CallbackRequest, response: Response, user: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    _require_connections()
    if not 20 <= len(body.state.get_secret_value()) <= 512:
        raise HTTPException(400, "Connection request is invalid")
    try:
        mailbox = connections.finish_connection(user_id=user.id, state=body.state.get_secret_value(),
            code=body.code.get_secret_value() if body.code else None, denied=body.denied)
        return PublicConnection.from_mailbox(mailbox)
    except connections.ConnectionError:
        raise HTTPException(400, "Connection request expired, was cancelled, or was already used") from None
    except ProviderError:
        raise HTTPException(400, "Microsoft authorization failed. Please connect again.") from None
    except credentials.CredentialError:
        raise HTTPException(503, "Credential storage is temporarily unavailable") from None


@router.delete("/connections/{connection_id}")
def disconnect(connection_id: str, response: Response, user: User = Depends(get_current_user)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    # Disconnect stays available when new connections/scanning are disabled.
    if not db.available():
        raise HTTPException(404, "Connection not found")
    try:
        pending = connections.disconnect(connection_id=connection_id, user_id=user.id)
        return {"disconnected": True, "subscription_cleanup_pending": pending}
    except connections.ConnectionError:
        raise HTTPException(404, "Connection not found") from None
