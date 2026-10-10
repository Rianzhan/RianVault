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

    # Auth tokens live in the api_tokens table (single source of truth).
    # Mint via: python scripts/create_token.py --role owner --name "..."

    import_max_file_mb: int = 512
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def redact_db_url(url: str) -> str:
    """日志里可以打印"连的是哪个库"，但绝不打印凭据。"""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        rest = rest.split("@", 1)[1]
    return f"{scheme}://{rest}"
