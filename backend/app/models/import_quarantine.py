import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.import_ import utcnow

JSONType = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


class ImportQuarantine(Base):
    """解析失败条目的隔离区：原始 payload 完整保留，绝不静默丢弃。"""

    __tablename__ = "import_quarantine"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    import_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("imports.id"), index=True
    )
    raw_payload: Mapped[dict] = mapped_column(JSONType)
    reason: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
