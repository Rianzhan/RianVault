import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.import_ import utcnow

JSONType = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class Memory(Base):
    """衍生记忆。所有修改走 memory_service（版本史 + 审计），不直接 UPDATE。

    event_time_start/end 用 date（事情发生的日期粒度），与 created_at
    （在 RianVault 创建的时间）和消息的 ingested_at（导入时间）严格区分。
    """

    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    body: Mapped[str] = mapped_column(sa.Text)
    memory_type: Mapped[str] = mapped_column(sa.String(30), default="note")
    status: Mapped[str] = mapped_column(sa.String(20), default="active", index=True)
    importance: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True)
    event_time_start: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    event_time_end: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    tags: Mapped[list] = mapped_column(JSONType, default=list)
    # DB 列名为 metadata（Declarative 属性名避开保留字）
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)
    current_version: Mapped[int] = mapped_column(sa.Integer, default=1)
    created_by_actor: Mapped[str] = mapped_column(sa.String(50))
    created_by_model: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
