import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.import_ import utcnow


class ApiToken(Base):
    """API token。只存 SHA-256 哈希（高熵随机 token 足够），明文只在创建时显示一次。

    role 即 actor：owner（Owner，全权限）/ zhan_mcp（受限写入）。
    """

    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(100))
    role: Mapped[str] = mapped_column(sa.String(20), index=True)  # owner | zhan_mcp
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
