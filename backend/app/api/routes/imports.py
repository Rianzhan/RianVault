import logging
import threading
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import require_owner
from app.core.logging_setup import LOGGER_NAME
from app.db.session import SessionLocal, get_db
from app.models import Import, ImportQuarantine
from app.schemas.import_ import ImportOut, ImportReport, QuarantineOut
from app.services import index_service
from app.services.importers.pipeline import ImportRejected, run_import

logger = logging.getLogger(LOGGER_NAME)

router = APIRouter(
    prefix="/api/imports",
    tags=["imports"],
    dependencies=[Depends(require_owner)],  # import 仅 owner（权限矩阵）
)


_auto_index_lock = threading.Lock()
_auto_index_running = False
_auto_index_pending = False


def _auto_index_worker() -> None:
    """串行化的建索引 worker：任一时刻**只允许一个**在跑。

    为什么必须串行（这是被真实崩溃教出来的）：
    建索引要用 bge-m3 跑 torch 推理，而**两个线程同时做 torch 推理会把整个进程搞崩**
    ——不是抛 Python 异常，是 access violation / 段错误，没有任何可捕获的东西。
    连着一次性导入十几个文件时，每个导入各起一个线程一起推理，必炸。
    所以这里压成串行：有人在跑时，后来的导入只标记 pending；
    当前批次跑完后 worker 再补一轮，既覆盖全部新消息，又绝不并发推理。
    """
    global _auto_index_running, _auto_index_pending
    try:
        while True:
            try:
                with SessionLocal() as db:
                    stats = index_service.index_messages(db)
                logger.info(
                    "导入后自动建索引完成：messages=%s chunks=%s",
                    stats["messages"],
                    stats["chunks"],
                )
            except (RuntimeError, OSError, ValueError):
                # Qdrant 目录被别的进程占着 / 依赖没装好：记下来，检索页可手动补齐。
                # 用 exception（带堆栈）——后台线程的失败必须看得见，不能静默。
                logger.exception("导入后自动建索引失败（检索页可手动补齐）")
            with _auto_index_lock:
                if not _auto_index_pending:
                    return
                _auto_index_pending = False
    finally:
        with _auto_index_lock:
            _auto_index_running = False


def schedule_auto_index() -> None:
    """导入完成后安排一轮建索引。可重复调用——并发调用只会串行地跑。"""
    global _auto_index_running, _auto_index_pending
    with _auto_index_lock:
        if _auto_index_running:
            # 已经有 worker 在跑：它结束前会再查一次 pending，这批新消息会被带上。
            _auto_index_pending = True
            return
        _auto_index_running = True
    threading.Thread(target=_auto_index_worker, daemon=True, name="auto-index").start()


@router.post("", response_model=ImportReport)
def create_import(
    file: UploadFile = File(...),
    source_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ImportReport:
    data = file.file.read()
    settings = get_settings()
    try:
        outcome = run_import(
            db,
            data,
            filename=file.filename or "unknown",
            source_type=source_type,
            max_file_mb=settings.import_max_file_mb,
        )
    except ImportRejected as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    quarantine = []
    if outcome.import_.status != "running":
        quarantine = list(
            db.scalars(
                select(ImportQuarantine).where(ImportQuarantine.import_id == outcome.import_.id)
            )
        )
    if settings.auto_index_after_import:
        schedule_auto_index()
    return ImportReport(
        already_imported=outcome.already_imported,
        import_=ImportOut.model_validate(outcome.import_),
        quarantine=[QuarantineOut.model_validate(q) for q in quarantine],
    )


@router.get("", response_model=list[ImportOut])
def list_imports(db: Session = Depends(get_db)) -> list[ImportOut]:
    rows = db.scalars(select(Import).order_by(Import.created_at.desc())).all()
    return [ImportOut.model_validate(r) for r in rows]


@router.get("/{import_id}", response_model=ImportReport)
def get_import(import_id: uuid.UUID, db: Session = Depends(get_db)) -> ImportReport:
    imp = db.get(Import, import_id)
    if imp is None:
        raise HTTPException(status_code=404, detail="import not found")
    quarantine = list(
        db.scalars(select(ImportQuarantine).where(ImportQuarantine.import_id == imp.id))
    )
    return ImportReport(
        already_imported=False,
        import_=ImportOut.model_validate(imp),
        quarantine=[QuarantineOut.model_validate(q) for q in quarantine],
    )
