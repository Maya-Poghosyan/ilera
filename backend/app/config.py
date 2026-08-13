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
    # Case that Poke's check-in replies are logged against when it doesn't name one.
    default_case_id: str = "demo"

    # Auth
    jwt_secret: str = "ilera-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 72

    # Redis. RAG index fallback for when DATABASE_URL is unset; nothing else uses it.
    redis_url: str = ""

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

    # Multi-agent (Band)
    band_rest_url: str = "https://app.band.ai"
    band_ws_url: str = "wss://app.band.ai/api/v1/socket/websocket"
    # Optional JSON registry mapping program group -> {agent_id, api_key} so each
    # specialist runs as its own Band agent. See band_agents.example.json.
    band_agents_file: str = "band_agents.json"
    # If true, the API process also hosts the Band agents. Set false to run them as their own
    # process (`python -m app.integrations.band`) so the agents' websockets and the API's
    # RAG/embedding memory don't share one container's memory limit.
    band_auto_start: bool = True

    # Integrations
    poke_api_key: str = ""
    # Shared secret Poke must present as a bearer token on the /mcp mount.
    # Empty disables the check (local development only).
    mcp_api_key: str = ""

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)

    @property
    def has_postgres(self) -> bool:
        return bool(self.database_url)

    @property
    def has_llm(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_band(self) -> bool:
        """True if a Band agent registry file is present."""
        import os
        path = self.band_agents_file
        if path and not os.path.isabs(path):
            path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path
            )
        return bool(path and os.path.exists(path))


@lru_cache
def get_settings() -> Settings:
    return Settings()
