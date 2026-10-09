"""Application settings. Real values live in .env (never committed); see .env.example."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Dev default: local sqlite file (zero-dependency). Prod: PostgreSQL via compose env.
    database_url: str = "sqlite:///./rianvault-dev.db"

    # Qdrant (needed from T6 on).
    qdrant_url: str = "http://localhost:6333"
    qdrant_minimal_payload: bool = False

    # Local embedding only. Model name is configuration, never hardcoded in business logic.
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"
    chunk_max_tokens: int = 600

    # Auth tokens (used from T4 on). Must be provided via .env; empty = auth not configured.
    rianvault_owner_token: str = ""
    rianvault_zhan_token: str = ""

    import_max_file_mb: int = 512
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
