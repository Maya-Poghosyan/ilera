"""Provider contract. OAuth state, token persistence, and job orchestration belong to callers."""

from __future__ import annotations

from typing import Protocol

from pydantic import AwareDatetime, BaseModel, SecretStr

from ..email_ingestion.models import EmailMessage, EmailProviderName


class OAuthTokens(BaseModel):
    access_token: SecretStr
    refresh_token: SecretStr
    expires_at: AwareDatetime
    scopes: list[str]


class AuthorizedMailbox(BaseModel):
    tokens: OAuthTokens
    provider_account_id: str
    mailbox_address: str | None = None
    tenant_id: str | None = None


class EmailSubscription(BaseModel):
    id: str
    expires_at: AwareDatetime


class EmailProvider(Protocol):
    name: EmailProviderName

    def authorize(self, *, state: str, code_challenge: str, nonce: str) -> str: ...

    async def exchange_code(self, *, code: str, code_verifier: str, nonce: str) -> AuthorizedMailbox: ...

    async def refresh_token(self, refresh_token: SecretStr) -> OAuthTokens: ...

    async def subscribe(
        self, access_token: SecretStr, *, notification_url: str, client_state: str
    ) -> EmailSubscription: ...

    async def renew_subscription(
        self, access_token: SecretStr, subscription_id: str
    ) -> EmailSubscription: ...

    async def fetch_message(self, access_token: SecretStr, message_id: str) -> EmailMessage: ...

    async def list_message_ids_since(
        self, access_token: SecretStr, *, since: AwareDatetime, max_ids: int = 500, max_pages: int = 20
    ) -> list[str]: ...

    async def unsubscribe(self, access_token: SecretStr, subscription_id: str) -> None: ...

    async def list_subscriptions(self, access_token: SecretStr, *, max_items: int = 100) -> list[dict]: ...

    async def revoke(self, tokens: OAuthTokens) -> None:
        """Provider-supported revocation; caller must also delete local credentials."""
        ...
