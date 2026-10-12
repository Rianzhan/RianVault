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
    return {
        "conversations": db.scalar(select(func.count(Conversation.id))) or 0,
        "messages": db.scalar(select(func.count(Message.id))) or 0,
        "memories": db.scalar(select(func.count(Memory.id)).where(Memory.status != "deleted")) or 0,
        "spans": db.scalar(
            select(func.count(MemorySourceSpan.id)).where(MemorySourceSpan.removed_at.is_(None))
        )
        or 0,
        "indexed_messages": indexed_messages,
        "unreviewed_candidates": db.scalar(
            select(func.count(MigrationReview.id)).where(MigrationReview.verdict == "unreviewed")
        )
        or 0,
        "actor": actor.role,
    }
