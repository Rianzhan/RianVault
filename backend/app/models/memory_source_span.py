import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.import_ import utcnow


class MemorySourceSpan(Base):
    """记忆来源片段。当前态 + 软移除；历史在 memory_versions 快照与 audit 中。

    支持：一条 memory 多个 span；span 覆盖一段连续消息；多个不连续 span；
    跨 conversation；后续增删（增删触发 memory 新版本 + 审计）。
    """

    __tablename__ = "memory_source_spans"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    memory_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("memories.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("conversations.id"), index=True
    )
    start_message_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("messages.id"), index=True
    )
    end_message_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("messages.id"), index=True
    )
    span_type: Mapped[str] = mapped_column(sa.String(10))  # evidence | context
    note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(sa.Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
    created_by_actor: Mapped[str] = mapped_column(sa.String(50))
    created_by_model: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    removed_by_actor: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
