"""Gmail delegated OAuth and Gmail API adapter (read-only), polled rather than pushed.

- Sign-in: authorization code with PKCE and a nonce; the ID token is verified against Google's keys
- Scope: gmail.readonly, which Google classes as restricted. Until the app passes Google's
  verification it runs as an unverified production app: users see a warning, and the Google
  Cloud project is capped at 100 users for its lifetime
- New mail: the hourly maintenance job lists inbox message ids received since the last pass
  (reconciliation.py); there is no Pub/Sub push or watch to renew
- No raw provider errors escape this boundary: they can contain tokens or message content
"""

from __future__ import annotations

import base64
import html
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote, urlencode

import httpx
from jose import jwt
from pydantic import SecretStr

from app.core.config import get_settings
from app.email_ingestion.models import EmailMessage
from app.email_ingestion.privacy import private_transport
from app.email_ingestion.providers.base import (AuthorizedMailbox, OAuthTokens, ProviderError,
                                                ReauthorizationRequired)

# Endpoints are module constants so the browser tests can point them at a local stand-in.
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
SCOPES = f"openid email {GMAIL_READONLY}"
MAX_RESPONSE_BYTES = 2_000_000


class GoogleEmailProvider:
    name: Literal["google"] = "google"

    def __init__(self, client_secret: SecretStr):
        settings = get_settings()  # client id and redirect are validated in Settings
        self.client_id = settings.email_google_client_id
        self.redirect_uri = settings.email_google_redirect_uri
        self.secret = client_secret

    def authorize(self, *, state: str, code_challenge: str, nonce: str) -> str:
        # offline + consent: Google returns a refresh token on every connection, including reconnects.
        return f"{AUTH_URL}?" + urlencode({
            "client_id": self.client_id, "response_type": "code", "redirect_uri": self.redirect_uri,
            "scope": SCOPES, "state": state, "code_challenge": code_challenge,
            "code_challenge_method": "S256", "nonce": nonce, "access_type": "offline",
            "prompt": "consent select_account",
        })

    @private_transport
    async def _token(self, fields: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(TOKEN_URL, data={
                    "client_id": self.client_id, "client_secret": self.secret.get_secret_value(), **fields,
                })
            data = response.json()
            if response.status_code == 400 and data.get("error") == "invalid_grant":
                raise ReauthorizationRequired("Google sign-in is required")
            if response.status_code != 200:
                raise ProviderError("Google authorization failed")
            return data
        except ReauthorizationRequired:
            raise
        except Exception:
            raise ProviderError("Google authorization failed") from None

    @staticmethod
    def _tokens(data: dict, previous_refresh: SecretStr | None = None) -> OAuthTokens:
        try:
            scopes = data["scope"].split()
            # Google's consent screen lets people untick Gmail access while still signing in.
            if GMAIL_READONLY not in scopes:
                raise ValueError("missing gmail.readonly")
            refresh = data.get("refresh_token") or (previous_refresh.get_secret_value() if previous_refresh else "")
            if not data["access_token"] or not refresh or data.get("token_type", "").lower() != "bearer":
                raise ValueError("invalid token response")
            seconds = int(data["expires_in"])
            if seconds <= 0:
                raise ValueError("expired token")
            return OAuthTokens(access_token=data["access_token"], refresh_token=refresh,
                               expires_at=datetime.now(timezone.utc) + timedelta(seconds=seconds), scopes=scopes)
        except Exception:
            raise ProviderError("Google did not grant mailbox access") from None

    @private_transport
    async def exchange_code(self, *, code: str, code_verifier: str, nonce: str) -> AuthorizedMailbox:
        data = await self._token({"grant_type": "authorization_code", "code": code,
                                  "code_verifier": code_verifier, "redirect_uri": self.redirect_uri})
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(CERTS_URL)
                response.raise_for_status()
                keys = response.json()
            claims = jwt.decode(data["id_token"], keys, algorithms=["RS256"], audience=self.client_id,
                                issuer=ISSUERS, access_token=data["access_token"],
                                options={"require_exp": True, "require_iat": True, "require_sub": True,
                                         "require_aud": True, "require_iss": True})
            if not secrets.compare_digest(claims.get("nonce", ""), nonce):
                raise ValueError("nonce mismatch")
            account_id, address = claims["sub"], claims.get("email")
            if not (isinstance(account_id, str) and account_id.isdigit() and len(account_id) <= 64):
                raise ValueError("invalid subject")
            if claims.get("email_verified") is not True or not isinstance(address, str):
                raise ValueError("unverified address")
        except Exception:
            raise ProviderError("Google account validation failed") from None
        return AuthorizedMailbox(tokens=self._tokens(data), provider_account_id=account_id,
                                 mailbox_address=address[:320])

    async def refresh_token(self, refresh_token: SecretStr) -> OAuthTokens:
        data = await self._token({"grant_type": "refresh_token", "refresh_token": refresh_token.get_secret_value()})
        return self._tokens(data, refresh_token)

    @private_transport
    async def _gmail(self, path: str, token: SecretStr, params: dict | None = None) -> dict:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                async with client.stream("GET", GMAIL_API + path, params=params, headers={
                    "Authorization": f"Bearer {token.get_secret_value()}",
                }) as response:
                    if response.status_code == 401:
                        raise ReauthorizationRequired("Google sign-in is required")
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ValueError("Message exceeds processing limit")
                        body.extend(chunk)
                    return json.loads(body)
        except ReauthorizationRequired:
            raise
        except Exception:
            raise ProviderError("Gmail request failed") from None

    async def fetch_message(self, access_token: SecretStr, message_id: str) -> EmailMessage:
        data = await self._gmail(f"/messages/{quote(message_id, safe='')}", access_token, {"format": "full"})
        try:
            payload = data["payload"]
            headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
            received = datetime.fromtimestamp(int(data["internalDate"]) / 1000, tz=timezone.utc)
            return EmailMessage(message_id=data["id"], received_at=received, sender=headers.get("from", ""),
                                subject=headers.get("subject", ""), body_text=_body_text(payload))
        except Exception:
            raise ProviderError("Gmail message could not be read") from None

    async def list_message_ids_since(
        self, access_token: SecretStr, *, since: datetime, max_ids: int = 500, max_pages: int = 20
    ) -> list[str]:
        """Identifiers of inbox messages received at or after `since`. Never fetches content."""
        params = {"labelIds": "INBOX", "q": f"after:{int(since.timestamp())}", "maxResults": "100"}
        ids: list[str] = []
        for _ in range(max_pages):
            data = await self._gmail("/messages", access_token, params)
            for item in data.get("messages", []):
                message_id = item.get("id") if isinstance(item, dict) else None
                if isinstance(message_id, str) and 1 <= len(message_id) <= 2048:
                    ids.append(message_id)
                    if len(ids) >= max_ids:
                        return ids
            page = data.get("nextPageToken")
            if not isinstance(page, str) or not page:
                break
            params = {**params, "pageToken": page}
        return ids

    @private_transport
    async def revoke(self, tokens: OAuthTokens) -> None:
        """Revoking the refresh token also ends every access token issued from it."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(REVOKE_URL, data={"token": tokens.refresh_token.get_secret_value()})
            # 400 means the grant is already gone, which is the goal.
            if response.status_code not in (200, 400):
                raise ValueError("revocation failed")
        except Exception:
            raise ProviderError("Google revocation failed") from None


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _parts(part: dict):
    yield part
    for child in part.get("parts") or []:
        yield from _parts(child)


def _body_text(payload: dict) -> str:
    """The message's plain-text body, or its HTML body reduced to text. Attachments are skipped."""
    found: dict[str, str] = {}
    for part in _parts(payload):
        mime, data = part.get("mimeType", ""), (part.get("body") or {}).get("data")
        if data and not part.get("filename") and mime in ("text/plain", "text/html") and mime not in found:
            found[mime] = _decode(data)
    if "text/plain" in found:
        return found["text/plain"]
    markup = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", found.get("text/html", ""))
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", markup)
    return re.sub(r"[ \t]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", markup))).strip()
