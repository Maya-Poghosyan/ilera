"""The one way this app authenticates to Azure services: its managed identity."""


def managed_identity(client_id: str = ""):
    """System-assigned identity, or the user-assigned one named by client_id."""
    from azure.identity import ManagedIdentityCredential

    return ManagedIdentityCredential(client_id=client_id or None)
