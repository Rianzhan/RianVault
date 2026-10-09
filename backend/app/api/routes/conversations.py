import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import require_any_role
from app.db.session import get_db
from app.models import Conversation, Message
from app.schemas.conversation import ConversationOut
from app.schemas.message import MessageOut

router = APIRouter(
    prefix="/api/conversations",
    tags=["conversations"],
    dependencies=[Depends(require_any_role)],
)


def _with_count(db: Session, conv: Conversation) -> ConversationOut:
    count = db.scalar(select(func.count(Message.id)).where(Message.conversation_id == conv.id))
    out = ConversationOut.model_validate(conv)
    out.message_count = count or 0
    return out


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    platform: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[ConversationOut]:
    stmt = select(Conversation).order_by(Conversation.started_at.desc().nulls_last())
    if platform:
        stmt = stmt.where(Conversation.source_platform == platform)
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return [_with_count(db, c) for c in rows]


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)) -> ConversationOut:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return _with_count(db, conv)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: uuid.UUID,
    around: uuid.UUID | None = Query(default=None, description="以某条消息为中心取前后窗口"),
    window: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    if db.get(Conversation, conversation_id) is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sort_order)
    )
    if around is not None:
        center = db.get(Message, around)
        if center is None or center.conversation_id != conversation_id:
            raise HTTPException(status_code=404, detail="anchor message not found")
        stmt = stmt.where(
            Message.sort_order >= center.sort_order - window,
            Message.sort_order <= center.sort_order + window,
        )
    else:
        stmt = stmt.offset(offset).limit(limit)
    return [MessageOut.model_validate(m) for m in db.scalars(stmt).all()]
