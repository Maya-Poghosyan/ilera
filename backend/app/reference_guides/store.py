"""Read guides from a dedicated private container, with a local fallback."""
import logging
from pathlib import Path

from ..config import get_settings

logger = logging.getLogger(__name__)
LOCAL_DIR = Path(__file__).resolve().parents[2] / 'data/reference_guides'
_client = None


def get_guide_bytes(key: str) -> bytes | None:
    global _client
    settings = get_settings()
    account = settings.reference_guides_blob_account_url or settings.forms_blob_account_url
    if account:
        try:
            if _client is None:
                from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
                from azure.storage.blob import BlobServiceClient
                credential = (ManagedIdentityCredential(client_id=settings.forms_managed_identity_client_id or None)
                              if settings.forms_use_managed_identity else DefaultAzureCredential())
                service = BlobServiceClient(account_url=account, credential=credential)
                _client = service.get_container_client(settings.reference_guides_blob_container)
            return _client.download_blob(key).readall()
        except Exception:
            logger.warning('Reference guide unavailable in blob storage: %s', key)
    path = LOCAL_DIR / key
    return path.read_bytes() if path.is_file() else None
