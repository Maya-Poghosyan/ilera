"""Fetch government PDF form templates.

These are authored reference binaries (e.g. CDSS/IHSS/SOC-873.pdf). They live in Azure
Blob Storage so the library can expand with state coverage without bloating Postgres or
the container image. The relative key is the form schema's _meta.pdf_path, identical to
the layout under data/forms/.

Blob-first with a local-file fallback: when no blob account is configured (local dev,
keyless boot, tests) the bundled files under data/forms/ are used, so form filling works
with zero services — the same fallback discipline as the policy and form-schema loaders.

Auth mirrors the email path: ManagedIdentityCredential in Azure, DefaultAzureCredential
otherwise. The SDK is imported lazily so environments without azure-storage-blob (and
the local-file path) are unaffected.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from ..config import get_settings

logger = logging.getLogger("ilera.forms.pdf_store")

FORMS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "forms")

_container_client = None


def _get_container_client():
    """Lazily build (and cache) the blob container client. Returns None if unconfigured."""
    global _container_client
    s = get_settings()
    if not s.has_forms_blob:
        return None
    if _container_client is None:
        from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
        from azure.storage.blob import BlobServiceClient

        credential = (
            ManagedIdentityCredential(client_id=s.forms_managed_identity_client_id or None)
            if s.forms_use_managed_identity
            else DefaultAzureCredential()
        )
        service = BlobServiceClient(account_url=s.forms_blob_account_url, credential=credential)
        _container_client = service.get_container_client(s.forms_blob_container)
    return _container_client


def _local_path(pdf_rel: str) -> Optional[str]:
    full = os.path.join(FORMS_DIR, pdf_rel)
    return full if os.path.exists(full) else None


def get_pdf_bytes(pdf_rel: str) -> Optional[bytes]:
    """Return the PDF's bytes for a relative key (e.g. 'CDSS/IHSS/SOC-873.pdf').

    Blob-first; falls back to the bundled file. None if neither has it.
    """
    if not pdf_rel:
        return None
    client = _get_container_client()
    if client is not None:
        try:
            return client.download_blob(pdf_rel).readall()
        except Exception:
            logger.warning("PDF blob fetch failed for %r; falling back to local file", pdf_rel)
    local = _local_path(pdf_rel)
    if local:
        with open(local, "rb") as fh:
            return fh.read()
    return None


def reset_client() -> None:
    """Drop the cached container client (tests that repoint config)."""
    global _container_client
    _container_client = None
