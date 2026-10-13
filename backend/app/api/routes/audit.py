"""审计流（append-only）：只读列表。

硬删除一条 memory 时，memory 本体连同版本/来源一起消失，
但这里仍会留下 `memory_purged` 事件——"它存在过、被谁删的"这件事本身可追溯。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_owner
from app.db.session import get_db
from app.models import ApiToken
from app.schemas.memory import AuditEventOut
from app.services import audit_service

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventOut])
def list_recent(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _actor: ApiToken = Depends(require_owner),
) -> list[AuditEventOut]:
    events = audit_service.list_recent(db, limit=limit)
    return [AuditEventOut.model_validate(e) for e in events]
