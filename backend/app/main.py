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


def _check_qdrant_exclusive() -> None:
    """启动自检：Qdrant 本地模式一个进程独占存储目录。

    两个 RianVault 进程同时跑，第二个要等到检索时才会 503——太晚了。
    现在启动时就试一下，占用了立刻大声说出来。
    """
    if get_settings().qdrant_mode != "local":
        return
    try:
        from qdrant_client import QdrantClient

        settings = get_settings()
        # 关键：**绝不能**用 index_service.get_qdrant() 来做这个检查。
        # 那会把进程内的 Qdrant 单例永久钉死在"启动时配置的目录"上——
        # 一旦后续要用别的路径/别的维度（测试用临时目录 + 替身模型就是如此），
        # 就会撞上 Vector dimension error。这里只用一个用完即弃的探针回答问题。
        probe = QdrantClient(path=settings.qdrant_path)
    except RuntimeError as e:
        msg = (
            "启动自检失败：另一个 RianVault 进程正在运行！\n"
            f"详情：{e}\n"
            "两个后端不能同时开。先停掉旧的（关掉那个 CMD 窗口，或 "
            "taskkill /F /IM python.exe 里对应的进程），再启动这个。"
        )
        logger.warning(msg)
        return
    try:
        probe.close()
    except OSError as e:  # 探针关不掉不影响"目录可用"这个结论
        logger.debug("关闭自检探针失败（忽略）：%s", e)
    logger.info("qdrant 本地目录独占检查通过")


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


_warmup_lock = threading.Lock()
_warmup_started = False


def start_warmup_once() -> None:
    """预热线程只允许起一次。

    重复加载同一个 4.3GB 的模型既没必要也危险：**多个线程同时跑 torch 会把进程搞崩**
    （实测 access violation，没有任何 Python 异常可抓）。用一个"已起过"的开关挡住并发。
    """
    global _warmup_started
    with _warmup_lock:
        if _warmup_started:
            return
        _warmup_started = True
    threading.Thread(target=_warmup_embedding, daemon=True, name="warmup").start()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时明确打印连的是哪个库（凭据脱敏）与本地 embedding 模型。

    私人记忆库最怕"写到错误的库里还以为成功"，所以这条必须可见。
    """
    settings = get_settings()
    logger.info("database=%s", redact_db_url(settings.database_url))
    logger.info("embedding_model=%s (local only)", settings.embedding_model)
    _check_qdrant_exclusive()
    if settings.warmup_embedding_on_startup:
        start_warmup_once()
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
