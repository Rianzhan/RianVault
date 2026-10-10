"""配置回归测试。

起因：alembic/env.py 自己解析 DATABASE_URL，而应用走 Settings，两套解析会漂移。
一次手误传了 RV_DATABASE_URL，迁移静默跑到了默认库上。这里锁死"单一来源"。
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, get_settings, redact_db_url

ALEMBIC_ENV = Path(__file__).resolve().parents[1] / "alembic" / "env.py"


def test_redact_db_url_hides_credentials() -> None:
    url = "postgresql+psycopg://rianvault:s3cr3t@db:5432/rianvault"
    redacted = redact_db_url(url)
    assert "s3cr3t" not in redacted
    assert redacted == "postgresql+psycopg://db:5432/rianvault"


def test_redact_db_url_keeps_sqlite_readable() -> None:
    assert redact_db_url("sqlite:///./rianvault-dev.db") == "sqlite:///./rianvault-dev.db"


def test_settings_reads_database_url_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/rianvault")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/rianvault"
    get_settings.cache_clear()


def test_alembic_uses_settings_not_its_own_env_parsing() -> None:
    """alembic 必须复用 Settings，否则会迁移到与运行时不同的库。"""
    source = ALEMBIC_ENV.read_text(encoding="utf-8")
    assert "get_settings()" in source
    assert "os.environ" not in source
