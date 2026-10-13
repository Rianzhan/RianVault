"""Application settings. Real values live in .env (never committed); see .env.example."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Dev default: local sqlite file (zero-dependency). Prod: PostgreSQL via compose env.
    database_url: str = "sqlite:///./rianvault-dev.db"

    # Qdrant（只是可重建的语义索引，权威真源始终在 PostgreSQL）。
    # mode=local 走进程内/本地文件存储（没装 docker 也能跑），mode=server 走 compose 容器。
    qdrant_mode: str = "local"
    qdrant_path: str = "./data/qdrant"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "rianvault_chunks"
    # True 时 payload 只留 chunk_id + conversation_id（其余过滤条件回查 PG）
    qdrant_minimal_payload: bool = False

    # Local embedding only. Model name is configuration, never hardcoded in business logic.
    # provider 决定实现，model 决定权重；两者都只在配置里出现。
    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"
    # CPU 上批量越大越划算（bge-m3 很重，batch 8 会慢一倍以上）
    embedding_batch_size: int = 32
    chunk_max_tokens: int = 600
    # 启动即预热：bge-m3 冷启动加载约 60 秒，不预热的话第一次检索要干等
    warmup_embedding_on_startup: bool = True
    # 导入完成后自动在后台补齐语义索引（人不用再手动点）
    auto_index_after_import: bool = True

    # Auth tokens live in the api_tokens table (single source of truth).
    # Mint via: python scripts/create_token.py --role owner --name "..."

    import_max_file_mb: int = 512

    # Portable Export 输出目录（.gitignore 已排除 exports/）
    export_dir: str = "./exports"

    log_level: str = "INFO"
    # 只在排查时打开：开启后未处理异常会打印完整堆栈（可能夹带 SQL 参数 = 正文）
    debug: bool = False

    # 加固：写操作与检索的每客户端限流（滑动窗口，按分钟计）
    rate_limit_per_minute: int = 120
    security_headers: bool = True


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
