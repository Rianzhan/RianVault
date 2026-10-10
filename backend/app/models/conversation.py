import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.import_ import utcnow

JSONType = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        sa.UniqueConstraint(
            "source_platform", "source_conversation_id", name="uq_conversations_source"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    source_platform: Mapped[str] = mapped_column(sa.String(50), index=True)
    source_conversation_id: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    title: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, index=True
    )
    import_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("imports.id"))
    # 导出文件中未映射的字段原样保留（列名避开 Declarative 保留字 metadata）
    raw_metadata: Mapped[dict] = mapped_column(JSONType, default=dict)
    # 源会话 id 缺失时的确定性哈希兜底
    dedup_hash: Mapped[str | None] = mapped_column(sa.String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)

    messages: Mapped[list["Message"]] = relationship(  # noqa: F821
        back_populates="conversation", order_by="Message.sort_order"
    )
