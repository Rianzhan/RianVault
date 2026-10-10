from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app import models  # noqa: F401  注册全部表
from app.core.config import get_settings
from app.db.base import Base

config = context.config
# 仅当 ini 里确实配置了 logging 段时才加载，避免缺段导致迁移被阻塞
if config.config_file_name is not None and config.get_section("loggers"):
    fileConfig(config.config_file_name)

# 单一来源：与运行时完全相同的 Settings（读 DATABASE_URL / .env）。
# 绝不要在这里另开一套环境变量解析 —— 曾经因为 alembic 读 DATABASE_URL、
# 我手误传 RV_DATABASE_URL，迁移跑到了别的库上（还顺手 drop 错了库）。
url = get_settings().database_url
config.set_main_option("sqlalchemy.url", url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
