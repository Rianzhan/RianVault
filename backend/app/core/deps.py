"""FastAPI 认证/授权依赖。

actor 一律由 token 派生（role 即 actor），客户端不得自行声明身份。
权限矩阵见 RIANVAULT_DESIGN_AUDIT.md 附 1。
"""

from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.db.session import get_db
from app.models import ApiToken


def get_current_actor(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ApiToken:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少 Bearer token")
    token_hash = hash_token(authorization.removeprefix("Bearer ").strip())
    row = db.scalar(
        select(ApiToken).where(
            ApiToken.token_hash == token_hash,
            ApiToken.revoked_at.is_(None),
        )
    )
    if row is None:
        raise HTTPException(status_code=401, detail="token 无效或已吊销")
    row.last_used_at = datetime.now(UTC)
    db.commit()
    return row


def require_any_role(actor: ApiToken = Depends(get_current_actor)) -> ApiToken:
    """owner 与 zhan_mcp 均可（read/search/create/edit/add_span）。"""
    return actor


def require_owner(actor: ApiToken = Depends(get_current_actor)) -> ApiToken:
    """仅 owner：delete / restore / import / export / token 管理 / reindex。"""
    if actor.role != "owner":
        raise HTTPException(status_code=403, detail="需要 owner 权限")
    return actor
