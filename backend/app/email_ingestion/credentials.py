"""Encrypt mailbox credentials in Postgres with a versioned key held in Azure Key Vault.

Key Vault contains the application secret and encryption keys; Postgres contains only
ciphertext. Never serialize OAuthTokens directly: SecretStr deliberately masks its JSON.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Iterator
from urllib.parse import urlparse

from pydantic import SecretStr

from ..config import get_settings
from ..providers.base import OAuthTokens


class CredentialError(Exception):
    """Fixed-message error safe to return without secret-bearing SDK details."""


@contextmanager
def _vault() -> Iterator:
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
    from azure.keyvault.secrets import SecretClient

    settings = get_settings()
    url = urlparse(settings.email_key_vault_url)
    if url.scheme != "https" or not url.hostname or not url.hostname.endswith(".vault.azure.net"):
        raise CredentialError("Key Vault is not configured")
    credential = (
        ManagedIdentityCredential(client_id=settings.email_managed_identity_client_id or None)
        if settings.email_use_managed_identity else DefaultAzureCredential()
    )
    with credential:
        with SecretClient(vault_url=settings.email_key_vault_url, credential=credential,
                          logging_enable=False, connection_timeout=5, read_timeout=10, retry_total=2) as client:
            yield client


def client_secret() -> SecretStr:
    try:
        with _vault() as client:
            value = client.get_secret(get_settings().email_microsoft_client_secret_name).value
        if not value:
            raise ValueError("empty secret")
        return SecretStr(value)
    except Exception:
        raise CredentialError("Mailbox credentials are unavailable") from None


def encrypt(payload: dict) -> str:
    from cryptography.fernet import Fernet

    try:
        with _vault() as client:
            secret = client.get_secret(get_settings().email_token_encryption_key_name)
        ciphertext = Fernet(secret.value.encode()).encrypt(json.dumps(payload).encode()).decode()
        return json.dumps({"key_version": secret.properties.version, "ciphertext": ciphertext})
    except Exception:
        raise CredentialError("Mailbox credentials are unavailable") from None


def decrypt(envelope: str) -> dict:
    from cryptography.fernet import Fernet

    try:
        sealed = json.loads(envelope)
        # Pin the key version so rotating the current key doesn't orphan existing records.
        if not sealed["key_version"]:
            raise ValueError("missing key version")
        with _vault() as client:
            secret = client.get_secret(
                get_settings().email_token_encryption_key_name, sealed["key_version"]
            )
        return json.loads(Fernet(secret.value.encode()).decrypt(sealed["ciphertext"].encode()))
    except Exception:
        raise CredentialError("Mailbox credentials are unavailable") from None


def seal_tokens(tokens: OAuthTokens) -> str:
    return encrypt({
        "access_token": tokens.access_token.get_secret_value(),
        "refresh_token": tokens.refresh_token.get_secret_value(),
        "expires_at": tokens.expires_at.isoformat(),
        "scopes": tokens.scopes,
    })


def open_tokens(envelope: str) -> OAuthTokens:
    try:
        return OAuthTokens.model_validate(decrypt(envelope))
    except Exception:
        raise CredentialError("Mailbox credentials are unavailable") from None
