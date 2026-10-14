from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_any_role
from app.db.session import get_db
from app.models import ApiToken

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/auth/me")
def who_am_i(
    actor: ApiToken = Depends(require_any_role),
    _db: Session = Depends(get_db),
) -> dict:
    """当前令牌的身份与角色。

    用途：让前端据此隐藏 Owner 专属操作（回收站 / 彻底删除 / 还原）。
    真正的权限判断永远在后端（依赖 require_owner），这里只是让界面别摆一个
    点了必然报 403 的按钮出来。
    """
    return {
        "id": str(actor.id),
        "name": actor.name,
        "role": actor.role,
        "can_admin": actor.role == "owner",
    }
