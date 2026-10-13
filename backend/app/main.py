import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import (
    admin_tokens,
    audit,
    conversations,
    export,
    health,
    imports,
    memories,
    messages,
    migration_audit,
    search,
    stats,
)
from app.core.config import get_settings, redact_db_url
from app.core.errors import install_exception_handlers
from app.core.logging_setup import setup_logging
from app.core.middleware import install_middleware

logger = setup_logging(get_settings().log_level)


def _warmup_embedding() -> None:
    """后台预热 embedding 模型。

    实测：bge-m3 冷启动加载约 60 秒。不预热的话，用户第一次点语义检索要干等一分钟，
    看起来就像"检索很慢"。预热后热态单次查询约 0.16 秒。
    """
    try:
        from app.services.embedding import get_embedding_provider

        provider = get_embedding_provider()
        provider.embed(["预热"])
        logger.info("embedding 模型已预热，首次检索不再等待")
    except (ImportError, OSError, RuntimeError, ValueError) as e:
        # 预热失败不能拖垮启动（依赖没装 / 权重缺失 / 目录被占）
        logger.warning("embedding 预热失败（不影响启动，首次检索时再加载）：%s", e)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时明确打印连的是哪个库（凭据脱敏）与本地 embedding 模型。

    私人记忆库最怕"写到错误的库里还以为成功"，所以这条必须可见。
    """
    settings = get_settings()
    logger.info("database=%s", redact_db_url(settings.database_url))
    logger.info("embedding_model=%s (local only)", settings.embedding_model)
    if settings.warmup_embedding_on_startup:
        threading.Thread(target=_warmup_embedding, daemon=True, name="warmup").start()
    yield


app = FastAPI(title="RianVault", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)  # 公开
app.include_router(imports.router)
app.include_router(conversations.router)
app.include_router(messages.router)
app.include_router(memories.router)
app.include_router(migration_audit.router)
app.include_router(search.router)
app.include_router(stats.router)
app.include_router(export.router)
app.include_router(audit.router)
app.include_router(admin_tokens.router)

# 加固：安全响应头 / 不缓存 / 限流（顺序：先加的后执行，Security 在最外层）
install_middleware(app)
# 统一异常处理：不吞异常，5xx 不返回成功字样
install_exception_handlers(app)
