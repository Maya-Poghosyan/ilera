from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Everything is optional so the app boots without keys."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    app_name: str = "Ilera API"
    cors_origins: str = "http://localhost:3000"
    # IANA zone reminder schedules are interpreted in ("18:00" means 6pm here).
    default_timezone: str = "America/Los_Angeles"
    # Auth
    jwt_secret: str = "ilera-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 72
    # Intake runs before signup, so an abandoned intake leaves a case nobody ever claims —
    # household data belonging to no account. Deleted after this many days; 0 keeps them.
    unclaimed_case_ttl_days: int = 5

    # LLM (OpenAI or an OpenAI-compatible endpoint such as Azure OpenAI)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # Optional OpenAI-compatible base URL (e.g. an Azure OpenAI v1 endpoint:
    # https://<resource>.openai.azure.com/openai/v1). Empty = api.openai.com.
    openai_base_url: str = ""
    embedding_model: str = "text-embedding-3-small"
    # Which embedding backend to use: "auto" (OpenAI if a key is set, else fastembed),
    # "openai", or "fastembed". Force "fastembed" when the OpenAI/Azure endpoint has no
    # embedding deployment (or to keep a fastembed-built index consistent).
    embedding_provider: str = "auto"
    # Local embedding model used when no OpenAI key is set (fastembed / ONNX, no API needed).
    fastembed_model: str = "BAAI/bge-small-en-v1.5"
    # Texts embedded per forward pass when indexing the corpus. Peak memory scales with it
    # (attention is O(batch x seq^2)): fastembed's own default of 256 needs several GB for
    # this corpus, which OOMs a small container.
    embedding_batch_size: int = 8
    # Texts per request when embedding through the hosted API, where the limit is round trips
    # rather than memory.
    embedding_api_batch_size: int = 128
    embedding_max_retries: int = 5
    embedding_timeout_seconds: float = 60.0
    # onnxruntime intra-op threads for the local embedding model. Each thread carries its own
    # activation arena, so keep it at 1 on a memory-constrained instance.
    embedding_threads: int = 1
    # Chunks written to the index per round trip when (re)building it.
    index_write_batch_size: int = 200
    # Postgres + pgvector connection string. The store of record for accounts, cases, and every
    # other record (see db.py). Also the RAG backend: the database does the KNN and holds the
    # chunk text, so this process only embeds one-line queries.
    database_url: str = ""

    # Azure Durable Functions (eligibility pipeline)
    # Base URL of the Function App, e.g. https://<app>.azurewebsites.net
    azure_functions_url: str = ""
    # Function-level host key for securing the HTTP starter endpoint.
    # Empty = no key header sent (use for local func host with anonymous auth).
    azure_functions_key: str = ""

    # Email verification (Azure Communication Services — covered under Azure BAA)
    # Connection string from your ACS resource. Without it the verification link is logged
    # to stdout so developers can click it locally without an email service configured.
    acs_email_connection_string: str = ""
    # Public base URL of the frontend, used to build the verification link in emails.
    app_url: str = "http://localhost:3000"
    # "From" address — must match a domain verified in your ACS Email resource.
    from_email: str = "noreply@ileracare.app"

    # Mailbox connection and scanning have independent rollout switches.
    email_connections_enabled: bool = False
    email_scanning_enabled: bool = False
    email_microsoft_tenant_id: str = ""
    email_microsoft_client_id: str = ""
    email_microsoft_redirect_uri: str = ""
    email_key_vault_url: str = ""
    email_microsoft_client_secret_name: str = "ilera-microsoft-client-secret"
    email_token_encryption_key_name: str = "ilera-email-token-key"
    email_service_bus_namespace: str = ""
    email_service_bus_queue: str = "email.scan"
    email_use_managed_identity: bool = True
    email_managed_identity_client_id: str = ""

    @property
    def has_postgres(self) -> bool:
        return bool(self.database_url)

    @property
    def has_llm(self) -> bool:
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
