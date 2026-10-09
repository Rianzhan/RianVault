"""Token 管理（仅 owner）。明文 token 只在创建响应中出现一次。"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_owner
from app.core.security import ROLES, generate_token, hash_token
from app.db.session import get_db
from app.models import ApiToken

router = APIRouter(
    prefix="/api/admin/tokens",
    tags=["admin"],
    dependencies=[Depends(require_owner)],
)


class TokenCreate(BaseModel):
    name: str
    role: str  # owner | zhan_mcp


class TokenOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class TokenCreatedOut(TokenOut):
    token: str  # 仅此一次，请立即保存


@router.post("", response_model=TokenCreatedOut)
def create_token(req: TokenCreate, db: Session = Depends(get_db)) -> TokenCreatedOut:
    if req.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role 必须是 {sorted(ROLES)} 之一")
    plaintext = generate_token()
    row = ApiToken(
        id=uuid.uuid4(),
        name=req.name,
        role=req.role,
        token_hash=hash_token(plaintext),
    )
    db.add(row)
    db.commit()
    return TokenCreatedOut(**TokenOut.model_validate(row).model_dump(), token=plaintext)


@router.get("", response_model=list[TokenOut])
def list_tokens(db: Session = Depends(get_db)) -> list[TokenOut]:
    rows = db.scalars(select(ApiToken).order_by(ApiToken.created_at)).all()
    return [TokenOut.model_validate(r) for r in rows]


@router.post("/{token_id}/revoke", response_model=TokenOut)
def revoke_token(token_id: uuid.UUID, db: Session = Depends(get_db)) -> TokenOut:
    row = db.get(ApiToken, token_id)
    if row is None:
        raise HTTPException(status_code=404, detail="token 不存在")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        db.commit()
    return TokenOut.model_validate(row)
