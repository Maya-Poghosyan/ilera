"""Fetch government PDF form templates from Azure Blob Storage.

These are authored reference binaries (e.g. CDSS/IHSS/SOC-873.pdf), kept in blob storage
so the library can grow with state coverage without bloating Postgres or the image. The
key is the form schema's _meta.pdf_path, identical to the layout under data/forms/ (the
authoring copies the generators read).
"""

from __future__ import annotations

from typing import Optional

from ..azure_identity import managed_identity
from ..config import get_settings

_container_client = None


def _get_container_client():
    global _container_client
    if _container_client is None:
        from azure.storage.blob import BlobServiceClient

        s = get_settings()
        if not s.forms_blob_account_url:
            raise RuntimeError("FORMS_BLOB_ACCOUNT_URL is required")
        service = BlobServiceClient(account_url=s.forms_blob_account_url,
                                    credential=managed_identity(s.forms_managed_identity_client_id))
        _container_client = service.get_container_client(s.forms_blob_container)
    return _container_client


def get_pdf_bytes(pdf_rel: str) -> Optional[bytes]:
    """The PDF's bytes for a relative key (e.g. 'CDSS/IHSS/SOC-873.pdf'); None if absent."""
    if not pdf_rel:
        return None
    from azure.core.exceptions import ResourceNotFoundError

    try:
        return _get_container_client().download_blob(pdf_rel).readall()
    except ResourceNotFoundError:
        return None
