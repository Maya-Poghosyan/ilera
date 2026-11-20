from functools import lru_cache
from typing import Literal

from pydantic import Field

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    The API, the Functions app and the email worker share this class and each sets only the
    settings it uses, so nothing is required here; code that needs a setting fails loudly
    when it is missing. There are no switches or fallbacks: unset means misconfigured."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    app_name: str = "Ilera API"
    cors_origins: str = "http://localhost:3000"
    # IANA zone reminder schedules are interpreted in ("18:00" means 6pm here).
    default_timezone: str = "America/Los_Angeles"
    # Auth
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 72
    # Intake runs before signup, so an abandoned intake leaves a case nobody ever claims —
    # household data belonging to no account. Deleted after this many days.
    unclaimed_case_ttl_days: int = Field(default=5, ge=1)

    # Eligibility research LLM: the Azure OpenAI v1 endpoint
    # (https://<resource>.openai.azure.com/openai/v1) and a deployment name on it.
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_base_url: str = ""
    # Completion budgets include reasoning tokens. Keep room for validated JSON.
    eligibility_max_output_tokens: int = Field(default=4096, ge=1024, le=16384)
    research_max_output_tokens: int = Field(default=3072, ge=1024, le=16384)
    agent_reasoning_effort: Literal["low", "medium", "high"] = "low"
    embedding_model: str = "text-embedding-3-small"
    # Texts per embeddings request; the limit is round trips rather than memory.
    embedding_api_batch_size: int = 128
    embedding_max_retries: int = 5
    embedding_timeout_seconds: float = 60.0
    # Chunks written to the index per round trip when (re)building it.
    index_write_batch_size: int = 200
    # Postgres + pgvector connection string. The store of record for accounts, cases, and every
    # other record (see db.py). Also the RAG backend: the database does the KNN and holds the
    # chunk text, so this process only embeds one-line queries.
    database_url: str = ""

    # Azure Durable Functions (eligibility pipeline)
    # Base URL of the Function App, e.g. https://<app>.azurewebsites.net
    azure_functions_url: str = ""
    # Function-level host key for the HTTP starter endpoint.
    azure_functions_key: str = ""

    # Email verification (Azure Communication Services — covered under Azure BAA)
    acs_email_connection_string: str = ""
    # Public base URL of the frontend, used to build the verification link in emails.
    app_url: str = "https://ileracare.app"
    # "From" address — must match a domain verified in your ACS Email resource.
    from_email: str = "noreply@ileracare.app"

    email_microsoft_tenant_id: str = ""
    email_microsoft_client_id: str = ""
    email_microsoft_redirect_uri: str = ""
    email_key_vault_url: str = ""
    email_microsoft_client_secret_name: str = "ilera-microsoft-client-secret"
    email_token_encryption_key_name: str = "ilera-email-token-key"
    email_service_bus_namespace: str = ""
    email_service_bus_queue: str = "email.scan"
    # Public API origin, bypassing the authenticated frontend API proxy.
    email_microsoft_notification_url: str = ""
    # User-assigned identity (worker); empty = the app's system-assigned identity.
    email_managed_identity_client_id: str = ""
    email_openai_endpoint: str = ""
    email_openai_deployment: str = ""
    email_scan_max_deliveries: int = 5

    # Intake document assistance: a dedicated Azure OpenAI resource, separate from eligibility
    # research and email scanning, reached with managed identity.
    document_openai_endpoint: str = ""      # e.g. https://<resource>.openai.azure.com
    document_openai_deployment: str = ""
    document_managed_identity_client_id: str = ""

    # Public reference guides (PDFs fetched from agencies) in Azure Blob Storage, read with the
    # API's managed identity. Form templates ship in the image under data/forms/.
    reference_guides_blob_account_url: str = ""  # e.g. https://ilerastorage.blob.core.windows.net
    reference_guides_blob_container: str = "reference-guides"


@lru_cache
def get_settings() -> Settings:
    return Settings()
