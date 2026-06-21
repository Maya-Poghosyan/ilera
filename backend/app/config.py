from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Everything is optional so the app boots without keys."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    app_name: str = "Ilera API"
    cors_origins: str = "http://localhost:3000"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
