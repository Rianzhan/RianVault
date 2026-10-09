"""审计服务：append-only。detail 只放轻量元信息，绝不放消息正文。"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent


def record(
    db: Session,
    *,
    event_type: str,
    actor: str,
    target_type: str,
    target_id: uuid.UUID,
    actor_model: str | None = None,
    detail: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        id=uuid.uuid4(),
        event_type=event_type,
        actor=actor,
        actor_model=actor_model,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
    )
    db.add(event)
    return event


def list_for_target(db: Session, target_type: str, target_id: uuid.UUID) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.target_type == target_type,
                AuditEvent.target_id == target_id,
            )
            .order_by(AuditEvent.created_at)
        ).all()
    )
