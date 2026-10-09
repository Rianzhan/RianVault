"""Source span 服务：增删都触发 memory 新版本（版本快照含 spans）。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Memory, MemorySourceSpan, Message
from app.services.memory_service import (
    MemoryNotFound,
    MemoryValidationError,
    bump_version_for_span_change,
)

SPAN_TYPES = {"evidence", "context"}


class SpanNotFound(LookupError):
    pass


def _validate_span(
    db: Session,
    memory: Memory,
    conversation_id: uuid.UUID,
    start_message_id: uuid.UUID,
    end_message_id: uuid.UUID,
    span_type: str,
) -> None:
    if memory.status == "deleted":
        raise MemoryValidationError("已删除的 memory 不能修改来源，请先 restore")
    if span_type not in SPAN_TYPES:
        raise MemoryValidationError(f"span_type 必须是 evidence 或 context，收到: {span_type}")

    start = db.get(Message, start_message_id)
    end = db.get(Message, end_message_id)
    if start is None or end is None:
        raise MemoryValidationError("start/end 消息不存在")
    if start.conversation_id != conversation_id or end.conversation_id != conversation_id:
        raise MemoryValidationError("start/end 消息必须属于指定的 conversation")
    if start.sort_order > end.sort_order:
        raise MemoryValidationError("start 消息必须不晚于 end 消息（按会话内顺序）")


def add_span(
    db: Session,
    memory_id: uuid.UUID,
    *,
    conversation_id: uuid.UUID,
    start_message_id: uuid.UUID,
    end_message_id: uuid.UUID,
    span_type: str,
    actor: str,
    actor_model: str | None = None,
    note: str | None = None,
    sort_order: int = 0,
    reason: str | None = None,
) -> MemorySourceSpan:
    memory = db.get(Memory, memory_id)
    if memory is None:
        raise MemoryNotFound("memory 不存在")
    _validate_span(db, memory, conversation_id, start_message_id, end_message_id, span_type)

    span = MemorySourceSpan(
        id=uuid.uuid4(),
        memory_id=memory_id,
        conversation_id=conversation_id,
        start_message_id=start_message_id,
        end_message_id=end_message_id,
        span_type=span_type,
        note=note,
        sort_order=sort_order,
        created_by_actor=actor,
        created_by_model=actor_model,
    )
    db.add(span)
    db.flush()
    bump_version_for_span_change(
        db,
        memory,
        actor=actor,
        actor_model=actor_model,
        reason=reason,
        event_type="span_added",
        span_id=span.id,
    )
    db.commit()
    return span


def remove_span(
    db: Session,
    span_id: uuid.UUID,
    *,
    actor: str,
    actor_model: str | None = None,
    reason: str | None = None,
) -> MemorySourceSpan:
    span = db.get(MemorySourceSpan, span_id)
    if span is None or span.removed_at is not None:
        raise SpanNotFound("span 不存在或已被移除")
    memory = db.get(Memory, span.memory_id)
    if memory is None:
        raise MemoryNotFound("memory 不存在")

    span.removed_at = datetime.now(UTC)
    span.removed_by_actor = actor
    db.flush()
    bump_version_for_span_change(
        db,
        memory,
        actor=actor,
        actor_model=actor_model,
        reason=reason,
        event_type="span_removed",
        span_id=span.id,
    )
    db.commit()
    return span
