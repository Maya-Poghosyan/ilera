"""Read public guide binaries from their own container in the forms storage account."""
from ..azure_identity import managed_identity
from ..config import get_settings

_client = None


def get_guide_bytes(key: str) -> bytes:
    global _client
    from azure.storage.blob import BlobServiceClient

    if _client is None:
        s = get_settings()
        if not s.forms_blob_account_url:
            raise RuntimeError("FORMS_BLOB_ACCOUNT_URL is required")
        service = BlobServiceClient(account_url=s.forms_blob_account_url,
                                    credential=managed_identity(s.forms_managed_identity_client_id))
        _client = service.get_container_client(s.reference_guides_blob_container)
    return _client.download_blob(key).readall()
