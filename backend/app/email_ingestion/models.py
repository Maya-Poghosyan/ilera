"""Contracts shared by mailbox connectors, notifications, and scan workers."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr

EmailProviderName = Literal["microsoft", "google"]


class MailboxConnection(BaseModel):
    """Server-only metadata; credentials live in encrypted storage, never this document."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    provider: EmailProviderName
    provider_account_id: str = Field(min_length=1)
    mailbox_address: str | None = Field(default=None, repr=False)
    tenant_id: str | None = None
    status: Literal["pending", "connected", "reauthorization_required", "disconnected"] = "pending"
    credential_id: str = Field(min_length=1, repr=False)
    granted_scopes: list[str] = Field(default_factory=list)
    consented_at: AwareDatetime
    subscription_id: str | None = None
    subscription_expires_at: AwareDatetime | None = None
    subscription_client_state_hash: str | None = Field(default=None, repr=False)
    subscription_renewal_required: bool = False
    reconciliation_required: bool = False
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EmailScanJob(BaseModel):
    """The complete queue payload: identifiers only, no subject, sender, body, or tokens."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    version: Literal[1] = 1
    provider: EmailProviderName
    connection_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=2048)

    @property
    def deduplication_id(self) -> str:
        identity = json.dumps(
            [self.version, self.provider, self.connection_id, self.message_id],
            separators=(",", ":"),
        )
        return hashlib.sha256(identity.encode()).hexdigest()


class EmailMessage(BaseModel):
    """Transient worker input. Never write to a store, queue, trace, or log."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    message_id: str
    received_at: AwareDatetime
    sender: SecretStr
    subject: SecretStr
    body_text: SecretStr


class ScanResult(BaseModel):
    """Minimal processing ledger; one entry per provider message and connection."""

    model_config = ConfigDict(extra="forbid")
    id: str  # EmailScanJob.deduplication_id
    connection_id: str
    user_id: str
    case_id: str
    provider: EmailProviderName
    message_id: str
    status: Literal["no_event", "suggested", "skipped", "failed"]
    suggested_event_ids: list[str] = Field(default_factory=list)
    model_version: str
    processed_at: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Fixed codes only: provider/model exception strings can contain email content.
    error_code: Literal["provider_unavailable", "invalid_extraction", "connection_inactive"] | None = None
