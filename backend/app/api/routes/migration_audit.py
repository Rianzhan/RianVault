import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import require_any_role, require_owner
from app.db.session import get_db
from app.models import ApiToken
from app.services import migration_audit_service as svc
from app.services.migration_audit_service import (
    CandidateNotFound,
    MigrationAuditError,
)

router = APIRouter(prefix="/api/audit/migration-candidates", tags=["migration-audit"])


class ScanRequest(BaseModel):
    scan_from: date
    scan_to: date
    source_platform: str | None = None


class ScanReport(BaseModel):
    created: int
    existing: int
    total: int


class CandidateOut(BaseModel):
    id: uuid.UUID
    matched_signal: str
    verdict: str
    signal_message: dict
    context: list[dict]
    context_start_message_id: uuid.UUID | None
    context_end_message_id: uuid.UUID | None
    linked_memory_id: uuid.UUID | None
    note: str | None


class VerdictRequest(BaseModel):
    verdict: str
    note: str | None = None


class CreateMemoryRequest(BaseModel):
    body: str
    span_type: str = "evidence"
    context_start_message_id: uuid.UUID | None = None
    context_end_message_id: uuid.UUID | None = None
    title: str | None = None
    memory_type: str = "note"
    event_time_start: date | None = None
    event_time_end: date | None = None
    tags: list[str] | None = None
    actor_model: str | None = None


def _errors(e: Exception) -> HTTPException:
    if isinstance(e, CandidateNotFound):
        return HTTPException(status_code=404, detail=str(e))
    return HTTPException(status_code=400, detail=str(e))


@router.post("/scan", response_model=ScanReport)
def scan(
    req: ScanRequest,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_owner),
) -> ScanReport:
    try:
        result = svc.scan(
            db,
            scan_from=req.scan_from,
            scan_to=req.scan_to,
            source_platform=req.source_platform,
        )
    except MigrationAuditError as e:
        raise _errors(e) from e
    return ScanReport(**result)


@router.get("", response_model=list[CandidateOut])
def list_candidates(
    verdict: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> list[CandidateOut]:
    return svc.list_candidates(db, verdict=verdict, limit=limit, offset=offset)


@router.post("/{review_id}/verdict")
def set_verdict(
    review_id: uuid.UUID,
    req: VerdictRequest,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> dict:
    try:
        row = svc.set_verdict(db, review_id, req.verdict, reviewed_by=actor.role, note=req.note)
    except (MigrationAuditError, CandidateNotFound) as e:
        raise _errors(e) from e
    return {"id": row.id, "verdict": row.verdict, "reviewed_by": row.reviewed_by}


@router.post("/{review_id}/create-memory")
def create_memory(
    review_id: uuid.UUID,
    req: CreateMemoryRequest,
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_any_role),
) -> dict:
    try:
        memory, row = svc.create_memory_from_candidate(
            db,
            review_id,
            body=req.body,
            actor=actor.role,
            actor_model=req.actor_model,
            span_type=req.span_type,
            context_start_message_id=req.context_start_message_id,
            context_end_message_id=req.context_end_message_id,
            title=req.title,
            memory_type=req.memory_type,
            event_time_start=req.event_time_start,
            event_time_end=req.event_time_end,
            tags=req.tags,
        )
    except (MigrationAuditError, CandidateNotFound) as e:
        raise _errors(e) from e
    return {
        "memory_id": memory.id,
        "current_version": memory.current_version,
        "linked_candidate_id": row.id,
        "verdict": row.verdict,
    }
