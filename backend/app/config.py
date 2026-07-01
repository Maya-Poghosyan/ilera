from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Everything is optional so the app boots without keys."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    app_name: str = "Ilera API"
    cors_origins: str = "http://localhost:3000"

    # Auth
    jwt_secret: str = "ilera-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 72

    # Redis (RAG + agent memory + document store)
    redis_url: str = ""

    # LLM
    llm_provider: str = "anthropic"  # "anthropic" | "openai"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    # Local embedding model used when no OpenAI key is set (fastembed / ONNX, no API needed).
    fastembed_model: str = "BAAI/bge-small-en-v1.5"

    # Multi-agent (Band)
    band_api_key: str = ""
    band_agent_id: str = ""
    band_rest_url: str = "https://app.band.ai"
    band_ws_url: str = "wss://app.band.ai/api/v1/socket/websocket"
    # Optional JSON registry mapping program group -> {agent_id, api_key} so each
    # specialist runs as its own Band agent. See band_agents.example.json.
    band_agents_file: str = "band_agents.json"
    # If true, Band agents auto-start on boot and process backlog (costs LLM credits).
    # Set false to keep agents offline until explicitly needed.
    band_auto_start: bool = False

    # Integrations
    poke_api_key: str = ""
    browserbase_api_key: str = ""
    browserbase_project_id: str = ""

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)

    @property
    def has_llm(self) -> bool:
        return bool(self.anthropic_api_key or self.openai_api_key)

    @property
    def has_band(self) -> bool:
        """True if Band is configured via env vars or a registry file."""
        if self.band_api_key and self.band_agent_id:
            return True
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
