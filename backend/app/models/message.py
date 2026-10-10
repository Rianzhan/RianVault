import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.import_ import utcnow

JSONType = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class Message(Base):
    """原始消息。导入后正文不可变：content_text / content_raw 永不出现在 UPDATE 中。

    模型标签的手工更正只写 source_model / source_model_note / model_label_source，
    且必须经过审计事件（T3 起）。
    """

    __tablename__ = "messages"
    __table_args__ = (
        sa.UniqueConstraint("conversation_id", "source_message_id", name="uq_messages_source_id"),
        sa.UniqueConstraint("conversation_id", "dedup_hash", name="uq_messages_dedup"),
        sa.Index("ix_messages_conv_sort", "conversation_id", "sort_order"),
        sa.Index("ix_messages_event_time", "event_time"),
        sa.Index("ix_messages_source_model", "source_model"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("conversations.id"), index=True
    )
    source_message_id: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    parent_source_message_id: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    sort_order: Mapped[int] = mapped_column(sa.Integer)
    role: Mapped[str] = mapped_column(sa.String(20))
    content_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    content_kind: Mapped[str] = mapped_column(sa.String(30), default="text")
    content_raw: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    # 事情真正发生的时间（源时间戳）——与 ingested_at（导入时间）严格区分
    event_time: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    event_time_raw: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
    source_model: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    source_model_note: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    # export / manual；第一阶段系统不做任何模型猜测（无 inferred）
    model_label_source: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    import_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("imports.id"))
    raw_metadata: Mapped[dict] = mapped_column(JSONType, default=dict)
    # 无源 id 时的确定性内容哈希（幂等第三层）
    dedup_hash: Mapped[str] = mapped_column(sa.String(64))

    conversation: Mapped["Conversation"] = relationship(  # noqa: F821
        back_populates="messages"
    )
