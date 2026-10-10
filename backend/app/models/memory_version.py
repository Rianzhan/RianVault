import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.import_ import utcnow

JSONType = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class MemoryVersion(Base):
    """全量快照版本史：append-only。

    snapshot 含该版本时点的 memory 全部字段 + 当时生效的 spans 列表。
    恢复快照 = 追加一个新版本，历史永不被改写。
    """

    __tablename__ = "memory_versions"
    __table_args__ = (
        sa.UniqueConstraint("memory_id", "version_number", name="uq_memory_versions_seq"),
        sa.Index("ix_memory_versions_mem_seq", "memory_id", "version_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    memory_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("memories.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(sa.Integer)
    snapshot: Mapped[dict] = mapped_column(JSONType)
    edited_by_actor: Mapped[str] = mapped_column(sa.String(50))
    edited_by_model: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    edit_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
