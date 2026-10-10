"""Chunk 索引登记：PostgreSQL 侧记录"哪些原文片段已经进了向量库"。

原则：Qdrant 是可丢弃、可重建的索引；本表才是"索引状态"的权威记录。
- vector_id 由 message_id + chunk_index 确定性推导（uuid5），所以重复 upsert 天然幂等。
- embedding_model 变了必须整库重建（换模型＝换向量空间），脚本靠这一列判断是否需要 rebuild。
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.import_ import utcnow


class ChunkIndex(Base):
    __tablename__ = "chunk_index"
    __table_args__ = (
        sa.UniqueConstraint("message_id", "chunk_index", name="uq_chunk_index_msg_pos"),
        sa.Index("ix_chunk_index_model", "embedding_model"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(sa.Integer)
    # Qdrant point id（uuid.uuid5 推导，重复写入同一 id）
    vector_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, unique=True)
    embedding_model: Mapped[str] = mapped_column(sa.String(120))
    token_estimate: Mapped[int] = mapped_column(sa.Integer)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
