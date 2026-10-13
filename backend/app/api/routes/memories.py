import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_any_role, require_owner
from app.db.session import get_db
from app.models import ApiToken, Memory
from app.schemas.memory import (
    ActorRequest,
    AuditEventOut,
    MemoryCreate,
    MemoryDetail,
    MemoryOut,
    MemoryPurgeResult,
    MemoryUpdate,
    RestoreRequest,
    SpanCreate,
    SpanOut,
    SpanUpdate,
    VersionOut,
)
from app.services import audit_service, memory_service, span_service
from app.services.memory_service import MemoryNotFound, MemoryValidationError
from app.services.span_service import SpanNotFound

router = APIRouter(prefix="/api/memories", tags=["memories"])


def _errors(e: Exception) -> HTTPException:
    if isinstance(e, MemoryNotFound | SpanNotFound):
        return HTTPException(status_code=404, detail=str(e))
    return HTTPException(status_code=400, detail=str(e))


@router.post("", response_model=MemoryOut)
def create_memory(
    req: MemoryCreate,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> MemoryOut:
    payload = req.model_dump()
    try:
        memory = memory_service.create_memory(db, actor=actor.role, **payload)
    except (MemoryValidationError, MemoryNotFound) as e:
        raise _errors(e) from e
    return MemoryOut.model_validate(memory)


@router.get("", response_model=list[MemoryOut])
def list_memories(
    status: str | None = Query(default=None, description="默认排除 deleted"),
    memory_type: str | None = Query(default=None),
    q: str | None = Query(default=None, description="标题/正文包含"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> list[MemoryOut]:
    stmt = select(Memory).order_by(Memory.updated_at.desc())
    if status:
        stmt = stmt.where(Memory.status == status)
    else:
        stmt = stmt.where(Memory.status != "deleted")
    if memory_type:
        stmt = stmt.where(Memory.memory_type == memory_type)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Memory.title.ilike(like) | Memory.body.ilike(like))
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return [MemoryOut.model_validate(m) for m in rows]


@router.get("/{memory_id}", response_model=MemoryDetail)
def get_memory_detail(
    memory_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> MemoryDetail:
    try:
        memory = memory_service._get(db, memory_id)
        spans = memory_service.active_spans(db, memory_id)
        versions = memory_service.list_versions(db, memory_id)
        events = audit_service.list_for_target(db, "memory", memory_id)
    except MemoryNotFound as e:
        raise _errors(e) from e
    return MemoryDetail(
        memory=MemoryOut.model_validate(memory),
        spans=[SpanOut.model_validate(s) for s in spans],
        versions=[VersionOut.model_validate(v) for v in versions],
        audit_events=[AuditEventOut.model_validate(a) for a in events],
    )


@router.patch("/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: uuid.UUID,
    req: MemoryUpdate,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> MemoryOut:
    payload = req.model_dump()
    actor_model = payload.pop("actor_model")
    reason = payload.pop("reason")
    changes = {k: v for k, v in payload.items() if v is not None or k in ("title", "importance")}
    try:
        memory = memory_service.update_memory(
            db,
            memory_id,
            actor=actor.role,
            actor_model=actor_model,
            reason=reason,
            **changes,
        )
    except (MemoryValidationError, MemoryNotFound) as e:
        raise _errors(e) from e
    return MemoryOut.model_validate(memory)


@router.delete("/{memory_id}", response_model=MemoryOut)
def delete_memory(
    memory_id: uuid.UUID,
    req: ActorRequest,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_owner),
) -> MemoryOut:
    try:
        memory = memory_service.soft_delete_memory(
            db,
            memory_id,
            actor=actor.role,
            actor_model=req.actor_model,
            reason=req.reason,
        )
    except MemoryNotFound as e:
        raise _errors(e) from e
    return MemoryOut.model_validate(memory)


@router.post("/{memory_id}/restore", response_model=MemoryOut)
def restore_memory(
    memory_id: uuid.UUID,
    req: RestoreRequest,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_owner),
) -> MemoryOut:
    try:
        memory = memory_service.restore_version(
            db,
            memory_id,
            req.version_number,
            actor=actor.role,
            actor_model=req.actor_model,
            reason=req.reason,
        )
    except (MemoryNotFound, MemoryValidationError) as e:
        raise _errors(e) from e
    return MemoryOut.model_validate(memory)


@router.post("/{memory_id}/spans", response_model=SpanOut)
def add_span(
    memory_id: uuid.UUID,
    req: SpanCreate,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> SpanOut:
    payload = req.model_dump()
    actor_model = payload.pop("actor_model")
    reason = payload.pop("reason")
    try:
        span = span_service.add_span(
            db,
            memory_id,
            actor=actor.role,
            actor_model=actor_model,
            reason=reason,
            **payload,
        )
    except (MemoryValidationError, MemoryNotFound, SpanNotFound) as e:
        raise _errors(e) from e
    return SpanOut.model_validate(span)


@router.delete("/{memory_id}/purge", response_model=MemoryPurgeResult)
def purge_memory(
    memory_id: uuid.UUID,
    req: ActorRequest | None = None,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_owner),
) -> MemoryPurgeResult:
    """回收站里的彻底删除（Owner only，物理删除 memory/版本/来源片段）。"""
    try:
        result = memory_service.purge_memory(
            db,
            memory_id,
            actor=actor.role,
            actor_model=req.actor_model if req else None,
            reason=req.reason if req else None,
        )
    except memory_service.MemoryNotFound as e:
        raise _errors(e) from e
    return MemoryPurgeResult.model_validate(result)


@router.patch("/{memory_id}/spans/{span_id}", response_model=SpanOut)
def update_span(
    memory_id: uuid.UUID,
    span_id: uuid.UUID,
    req: SpanUpdate,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> SpanOut:
    """调整来源片段的起止范围（圈错了可以改，会留新版本 + before/after 审计）。"""
    try:
        span = span_service.update_span(
            db,
            span_id,
            start_message_id=req.start_message_id,
            end_message_id=req.end_message_id,
            span_type=req.span_type,
            note=req.note,
            actor=actor.role,
            actor_model=req.actor_model,
            reason=req.reason,
        )
    except (MemoryValidationError, MemoryNotFound, SpanNotFound) as e:
        raise _errors(e) from e
    return SpanOut.model_validate(span)


@router.delete("/{memory_id}/spans/{span_id}", response_model=SpanOut)
def remove_span(
    memory_id: uuid.UUID,
    span_id: uuid.UUID,
    req: ActorRequest,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> SpanOut:
    try:
        span = span_service.remove_span(
            db,
            span_id,
            actor=actor.role,
            actor_model=req.actor_model,
            reason=req.reason,
        )
    except (SpanNotFound, MemoryNotFound) as e:
        raise _errors(e) from e
    return SpanOut.model_validate(span)


@router.get("/{memory_id}/versions", response_model=list[VersionOut])
def list_versions(
    memory_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> list[VersionOut]:
    try:
        versions = memory_service.list_versions(db, memory_id)
    except MemoryNotFound as e:
        raise _errors(e) from e
    return [VersionOut.model_validate(v) for v in versions]


@router.get("/{memory_id}/audit", response_model=list[AuditEventOut])
def list_audit(
    memory_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> list[AuditEventOut]:
    if db.get(Memory, memory_id) is None:
        raise HTTPException(status_code=404, detail="memory 不存在")
    events = audit_service.list_for_target(db, "memory", memory_id)
    return [AuditEventOut.model_validate(a) for a in events]
