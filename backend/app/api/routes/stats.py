"""档案馆概览统计（首页用）。只返回计数，不返回任何正文。"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import require_any_role
from app.db.session import get_db
from app.models import (
    ApiToken,
    ChunkIndex,
    Conversation,
    Memory,
    MemorySourceSpan,
    Message,
    MigrationReview,
)

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats(
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> dict:
    indexed_messages = db.scalar(select(func.count(func.distinct(ChunkIndex.message_id)))) or 0
    # 只有"有正文"的消息才需要进语义索引；纯图片/空消息不进索引，也不算"漏"
    indexable_messages = (
        db.scalar(
            select(func.count(Message.id))
            .where(Message.content_text.is_not(None))
            .where(func.trim(Message.content_text) != "")
        )
        or 0
    )
    return {
        "conversations": db.scalar(select(func.count(Conversation.id))) or 0,
        "messages": db.scalar(select(func.count(Message.id))) or 0,
        "memories": db.scalar(select(func.count(Memory.id)).where(Memory.status != "deleted")) or 0,
        "spans": db.scalar(
            select(func.count(MemorySourceSpan.id)).where(MemorySourceSpan.removed_at.is_(None))
        )
        or 0,
        "indexed_messages": indexed_messages,
        # 检索页"索引是否覆盖"用它做分母，避免把空正文消息误判成"漏索引"
        "indexable_messages": indexable_messages,
        "unreviewed_candidates": db.scalar(
            select(func.count(MigrationReview.id)).where(MigrationReview.verdict == "unreviewed")
        )
        or 0,
        "actor": actor.role,
    }
