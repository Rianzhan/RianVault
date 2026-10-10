import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JSONType = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Import(Base):
    """导入台账。checksum_sha256 唯一：同一文件重复导入不产生新数据。"""

    __tablename__ = "imports"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    source_type: Mapped[str] = mapped_column(sa.String(50))
    original_filename: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    checksum_sha256: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)
    file_size_bytes: Mapped[int] = mapped_column(sa.BigInteger)
    adapter_version: Mapped[str] = mapped_column(sa.String(50))
    # running / completed / failed（"already_imported" 只是响应状态，不落库）
    status: Mapped[str] = mapped_column(sa.String(20), default="running")
    stats: Mapped[dict] = mapped_column(JSONType, default=dict)
    warnings: Mapped[list] = mapped_column(JSONType, default=list)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
