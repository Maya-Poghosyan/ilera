"""Read public guide binaries from blob storage."""
from app.core.azure_identity import managed_identity
from app.core.config import get_settings

_client = None


def get_guide_bytes(key: str) -> bytes:
    global _client
    from azure.storage.blob import BlobServiceClient

    if _client is None:
        s = get_settings()
        service = BlobServiceClient(account_url=s.reference_guides_blob_account_url,
                                    credential=managed_identity())
        _client = service.get_container_client("reference-guides")
    return _client.download_blob(key).readall()
