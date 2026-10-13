"""检索 API。

- 用 POST 而不是 GET：query 属于私人内容，不能出现在 URL / access log 里。
- 返回体里只带正文（给 Owner 自己看），服务端日志只记命中数。
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import require_any_role, require_owner
from app.db.session import get_db
from app.models import ApiToken, ChunkIndex
from app.services import index_service, search_service
from app.services.search_service import Filters

router = APIRouter(prefix="/api", tags=["search"])


class SearchFilters(BaseModel):
    source_platform: str | None = None
    conversation_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    role: str | None = None
    source_model: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    mode: str = Field(default="hybrid", pattern="^(keyword|semantic|hybrid)$")
    limit: int = Field(default=20, ge=1, le=100)
    filters: SearchFilters | None = None


class SearchResponse(BaseModel):
    mode: str
    count: int
    hits: list[dict]


class IndexRequest(BaseModel):
    rebuild: bool = False
    limit_messages: int | None = Field(default=None, ge=1)


@router.post("/search", response_model=SearchResponse)
def search(
    req: SearchRequest,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> SearchResponse:
    filters = None
    if req.filters:
        filters = Filters(
            source_platform=req.filters.source_platform,
            conversation_id=str(req.filters.conversation_id)
            if req.filters.conversation_id
            else None,
            date_from=req.filters.date_from,
            date_to=req.filters.date_to,
            role=req.filters.role,
            source_model=req.filters.source_model,
        )
    try:
        hits = search_service.search(db, req.query, mode=req.mode, limit=req.limit, filters=filters)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        # 例如本地 embedding 依赖未安装：如实报 503，不假装有结果
        raise HTTPException(status_code=503, detail=str(e)) from e
    return SearchResponse(mode=req.mode, count=len(hits), hits=[h.as_dict() for h in hits])


@router.get("/index/status")
def index_status(
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> dict:
    rows = db.execute(
        select(ChunkIndex.embedding_model, func.count(ChunkIndex.id)).group_by(
            ChunkIndex.embedding_model
        )
    ).all()
    return {
        "models": {model: count for model, count in rows},
        "total_chunks": sum(count for _, count in rows),
        "collection": index_service_collection_name(),
    }


def index_service_collection_name() -> str:
    from app.core.config import get_settings

    return get_settings().qdrant_collection


@router.post("/index/build")
def build_index(
    req: IndexRequest,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_owner),
) -> dict:
    """增量或全量重建索引（Owner only）。耗时操作，失败会如实抛出。"""
    try:
        stats = index_service.index_messages(
            db, rebuild=req.rebuild, limit_messages=req.limit_messages
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return stats


@router.get("/index/chunks")
def list_chunks(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> list[dict]:
    rows = db.scalars(select(ChunkIndex).limit(limit)).all()
    return [
        {
            "message_id": str(r.message_id),
            "chunk_index": r.chunk_index,
            "vector_id": str(r.vector_id),
            "embedding_model": r.embedding_model,
            "token_estimate": r.token_estimate,
        }
        for r in rows
    ]
