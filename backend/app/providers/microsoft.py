"""Microsoft 365 delegated OAuth and Graph adapter for one approved tenant.

No raw provider errors escape this boundary: they can contain tokens or message content.
"""

from __future__ import annotations

import secrets
import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote, urlencode, urlparse
from uuid import UUID

import httpx
from jose import jwt
from pydantic import SecretStr

from ..config import get_settings
from ..email_ingestion.models import EmailMessage
from ..email_ingestion.privacy import private_transport
from .base import AuthorizedMailbox, EmailSubscription, OAuthTokens

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = "openid profile offline_access https://graph.microsoft.com/Mail.Read"
CONSUMER_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"


class ProviderError(Exception):
    pass


class ReauthorizationRequired(ProviderError):
    pass


class MicrosoftEmailProvider:
    name: Literal["microsoft"] = "microsoft"

    def __init__(self, client_secret: SecretStr):
        settings = get_settings()
        try:
            self.tenant = str(UUID(settings.email_microsoft_tenant_id))
            self.client_id = str(UUID(settings.email_microsoft_client_id))
            if self.tenant == CONSUMER_TENANT:
                raise ValueError("consumer account")
            redirect = urlparse(settings.email_microsoft_redirect_uri)
            if (redirect.scheme != "https" or not redirect.netloc or redirect.query or redirect.fragment
                    or redirect.path != "/api/email/microsoft/callback"):
                raise ValueError("invalid redirect")
        except ValueError:
            raise ProviderError("Microsoft mailbox connection is not configured") from None
        self.redirect_uri = settings.email_microsoft_redirect_uri
        self.secret = client_secret
        self.authority = f"https://login.microsoftonline.com/{self.tenant}"

    def authorize(self, *, state: str, code_challenge: str, nonce: str) -> str:
        return f"{self.authority}/oauth2/v2.0/authorize?" + urlencode({
            "client_id": self.client_id, "response_type": "code", "response_mode": "query",
            "redirect_uri": self.redirect_uri, "scope": SCOPES, "state": state,
            "code_challenge": code_challenge, "code_challenge_method": "S256",
            "nonce": nonce, "prompt": "select_account",
        })

    @private_transport
    async def _token(self, fields: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(f"{self.authority}/oauth2/v2.0/token", data={
                    "client_id": self.client_id, "client_secret": self.secret.get_secret_value(),
                    "scope": SCOPES, **fields,
                })
            data = response.json()
            if response.status_code == 400 and data.get("error") in {"invalid_grant", "interaction_required"}:
                raise ReauthorizationRequired("Microsoft sign-in is required")
            if response.status_code != 200:
                raise ProviderError("Microsoft authorization failed")
            return data
        except ReauthorizationRequired:
            raise
        except Exception:
            raise ProviderError("Microsoft authorization failed") from None

    @staticmethod
    def _tokens(data: dict, previous_refresh: SecretStr | None = None) -> OAuthTokens:
        try:
            scopes = data["scope"].split()
            if not any(s.lower().removeprefix("https://graph.microsoft.com/") == "mail.read" for s in scopes):
                raise ValueError("missing Mail.Read")
            refresh = data.get("refresh_token") or (previous_refresh.get_secret_value() if previous_refresh else "")
            if not data["access_token"] or not refresh or data.get("token_type", "").lower() != "bearer":
                raise ValueError("invalid token response")
            seconds = int(data["expires_in"])
            if seconds <= 0:
                raise ValueError("expired token")
            return OAuthTokens(access_token=data["access_token"], refresh_token=refresh,
                               expires_at=datetime.now(timezone.utc) + timedelta(seconds=seconds), scopes=scopes)
        except Exception:
            raise ProviderError("Microsoft did not grant mailbox access") from None

    @private_transport
    async def exchange_code(self, *, code: str, code_verifier: str, nonce: str) -> AuthorizedMailbox:
        data = await self._token({"grant_type": "authorization_code", "code": code,
                                  "code_verifier": code_verifier, "redirect_uri": self.redirect_uri})
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(f"{self.authority}/discovery/v2.0/keys")
                response.raise_for_status()
                keys = response.json()
            claims = jwt.decode(data["id_token"], keys, algorithms=["RS256"],
                                audience=self.client_id, issuer=f"{self.authority}/v2.0",
                                access_token=data["access_token"],
                                options={"require_exp": True, "require_iat": True, "require_sub": True,
                                         "require_aud": True, "require_iss": True})
            if claims.get("tid") != self.tenant or not secrets.compare_digest(claims.get("nonce", ""), nonce):
                raise ValueError("identity mismatch")
            account_id = str(UUID(claims["oid"]))
        except Exception:
            raise ProviderError("Microsoft account validation failed") from None
        address = claims.get("preferred_username")
        return AuthorizedMailbox(tokens=self._tokens(data), provider_account_id=account_id,
                                 mailbox_address=address[:320] if isinstance(address, str) else None,
                                 tenant_id=self.tenant)

    async def refresh_token(self, refresh_token: SecretStr) -> OAuthTokens:
        data = await self._token({"grant_type": "refresh_token", "refresh_token": refresh_token.get_secret_value()})
        return self._tokens(data, refresh_token)

    @private_transport
    async def _graph(self, method: str, path: str, token: SecretStr, **kwargs) -> dict:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                async with client.stream(method, GRAPH + path, headers={
                    "Authorization": f"Bearer {token.get_secret_value()}",
                    "Prefer": 'IdType="ImmutableId", outlook.body-content-type="text"',
                }, **kwargs) as response:
                    if method == "DELETE" and response.status_code in (204, 404):
                        return {}
                    if response.status_code == 401:
                        raise ReauthorizationRequired("Microsoft sign-in is required")
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > 2_000_000:
                            raise ValueError("Message exceeds processing limit")
                        body.extend(chunk)
                    return json.loads(body)
        except ReauthorizationRequired:
            raise
        except Exception:
            raise ProviderError("Microsoft mailbox request failed") from None

    async def fetch_message(self, access_token: SecretStr, message_id: str) -> EmailMessage:
        data = await self._graph("GET", f"/me/messages/{quote(message_id, safe='')}", access_token,
                                 params={"$select": "id,sender,subject,receivedDateTime,body"})
        try:
            if data["body"]["contentType"].lower() != "text":
                raise ValueError("expected text")
            return EmailMessage(message_id=data["id"], received_at=data["receivedDateTime"],
                                sender=data.get("sender", {}).get("emailAddress", {}).get("address", ""),
                                subject=data.get("subject", ""), body_text=data["body"]["content"])
        except Exception:
            raise ProviderError("Microsoft message could not be read") from None

    async def list_message_ids_since(
        self, access_token: SecretStr, *, since: datetime, max_ids: int = 500, max_pages: int = 20
    ) -> list[str]:
        """Identifiers for messages received at or after `since`, oldest first.

        Reconciliation only — never fetches bodies, subjects, or senders. The result is
        bounded by `max_ids`/`max_pages`; a mailbox with more unrecovered mail than the
        bound keeps `reconciliation_required` set so a later pass continues. Paging follows
        Graph's `@odata.nextLink` but re-selects `id` defensively and ignores non-string ids.
        """
        # A tiny margin absorbs clock skew between our cursor and the server's timestamps.
        filter_ts = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        params: dict | None = {
            "$select": "id",
            "$filter": f"receivedDateTime ge {filter_ts}",
            "$orderby": "receivedDateTime asc",
            "$top": "50",
        }
        path = "/me/messages"
        ids: list[str] = []
        for _ in range(max_pages):
            data = await self._graph("GET", path, access_token, params=params)
            for item in data.get("value", []):
                message_id = item.get("id") if isinstance(item, dict) else None
                if isinstance(message_id, str) and 1 <= len(message_id) <= 2048:
                    ids.append(message_id)
                    if len(ids) >= max_ids:
                        return ids
            next_link = data.get("@odata.nextLink")
            if not isinstance(next_link, str) or not next_link.startswith(GRAPH):
                break
            # nextLink carries its own opaque query; pass it as an absolute path with no extra params.
            path = next_link[len(GRAPH):]
            params = None
        return ids

    async def subscribe(self, access_token: SecretStr, *, notification_url: str,
                        client_state: str) -> EmailSubscription:
        if urlparse(notification_url).scheme != "https":
            raise ProviderError("An HTTPS notification URL is required")
        data = await self._graph("POST", "/subscriptions", access_token, json={
            "changeType": "created", "notificationUrl": notification_url,
            "lifecycleNotificationUrl": notification_url,
            "resource": "me/messages", "clientState": client_state,
            "expirationDateTime": (datetime.now(timezone.utc) + timedelta(days=6)).isoformat(),
        })
        return self._subscription(data)

    @staticmethod
    def _subscription(data: dict) -> EmailSubscription:
        try:
            return EmailSubscription(id=data["id"], expires_at=data["expirationDateTime"])
        except Exception:
            raise ProviderError("Microsoft subscription response was invalid") from None

    async def renew_subscription(self, access_token: SecretStr, subscription_id: str) -> EmailSubscription:
        data = await self._graph("PATCH", f"/subscriptions/{quote(subscription_id, safe='')}", access_token,
                                 json={"expirationDateTime": (datetime.now(timezone.utc) + timedelta(days=6)).isoformat()})
        return self._subscription(data)

    async def unsubscribe(self, access_token: SecretStr, subscription_id: str) -> None:
        await self._graph("DELETE", f"/subscriptions/{quote(subscription_id, safe='')}", access_token)

    async def list_subscriptions(self, access_token: SecretStr, *, max_items: int = 100) -> list[dict]:
        """Active Graph subscriptions visible to this delegated token.

        Reconciliation only. Returns minimal dicts ``{"id", "notification_url", "resource"}`` so
        the caller can identify subscriptions that point at our notification URL but are no
        longer tracked in the database (leaked when a create preceded a failed DB commit).
        No message content is involved; ids are opaque subscription identifiers, not mailbox data.
        """
        data = await self._graph("GET", "/subscriptions", access_token)
        result: list[dict] = []
        for item in data.get("value", []):
            if not isinstance(item, dict):
                continue
            sub_id = item.get("id")
            if not isinstance(sub_id, str) or not 1 <= len(sub_id) <= 256:
                continue
            result.append({
                "id": sub_id,
                "notification_url": item.get("notificationUrl") if isinstance(item.get("notificationUrl"), str) else None,
                "resource": item.get("resource") if isinstance(item.get("resource"), str) else None,
            })
            if len(result) >= max_items:
                break
        return result

    async def revoke(self, tokens: OAuthTokens) -> None:
        # Microsoft has no narrow RFC 7009 revocation endpoint for these delegated tokens.
        # Caller deletes local tokens and subscriptions. Tenant-wide session revocation
        # would require excessive permissions and disrupt unrelated user sessions.
        return None
