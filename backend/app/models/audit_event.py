import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.import_ import utcnow

JSONType = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class AuditEvent(Base):
    """审计事件：append-only。detail 只放轻量元信息（版本号、id、计数），
    不放消息正文。"""

    __tablename__ = "audit_events"
    __table_args__ = (
        sa.Index("ix_audit_events_target", "target_type", "target_id"),
        sa.Index("ix_audit_events_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(sa.String(50), index=True)
    actor: Mapped[str] = mapped_column(sa.String(50))
    actor_model: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    target_type: Mapped[str] = mapped_column(sa.String(50))
    target_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid)
    detail: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
