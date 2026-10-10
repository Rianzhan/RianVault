import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.import_ import utcnow

VERDICTS = {
    "unreviewed",
    "successful_write",
    "failed_write",
    "retry_success",
    "edit",
    "delete",
    "uncertain",
    "ignore",
}


class MigrationReview(Base):
    """遗失记忆打捞候选。命中信号 ≠ 真实记忆写入：默认 unreviewed，
    必须由 Owner 展示上下文后人工判定。"""

    __tablename__ = "migration_reviews"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    signal_message_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("messages.id"), unique=True, index=True
    )
    scan_from: Mapped[date] = mapped_column(sa.Date)
    scan_to: Mapped[date] = mapped_column(sa.Date)
    matched_signal: Mapped[str] = mapped_column(sa.String(200))
    verdict: Mapped[str] = mapped_column(sa.String(20), default="unreviewed", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    # Owner 建记忆时选定的上下文范围（可以比信号消息本身大）
    context_start_message_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("messages.id"), nullable=True
    )
    context_end_message_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("messages.id"), nullable=True
    )
    linked_memory_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("memories.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
