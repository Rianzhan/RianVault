"""Memory 领域服务：唯一写入路径。

任何 memory 变更（含 spans 增删、删除、恢复）都产生一个新的全量快照版本
和一条审计事件。历史版本永不被修改。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Memory, MemorySourceSpan, MemoryVersion
from app.services import audit_service

MEMORY_TYPES = {"fact", "preference", "event", "relationship", "goal", "note"}
MEMORY_STATUSES = {"draft", "active", "archived", "deleted"}


class MemoryNotFound(LookupError):
    pass


class MemoryValidationError(ValueError):
    pass


def _get(db: Session, memory_id: uuid.UUID) -> Memory:
    memory = db.get(Memory, memory_id)
    if memory is None:
        raise MemoryNotFound("memory 不存在")
    return memory


def active_spans(db: Session, memory_id: uuid.UUID) -> list[MemorySourceSpan]:
    return list(
        db.scalars(
            select(MemorySourceSpan)
            .where(
                MemorySourceSpan.memory_id == memory_id,
                MemorySourceSpan.removed_at.is_(None),
            )
            .order_by(MemorySourceSpan.sort_order, MemorySourceSpan.created_at)
        ).all()
    )


def build_snapshot(memory: Memory, spans: list[MemorySourceSpan]) -> dict:
    return {
        "title": memory.title,
        "body": memory.body,
        "memory_type": memory.memory_type,
        "status": memory.status,
        "importance": memory.importance,
        "event_time_start": (
            memory.event_time_start.isoformat() if memory.event_time_start else None
        ),
        "event_time_end": (memory.event_time_end.isoformat() if memory.event_time_end else None),
        "tags": list(memory.tags or []),
        "extra_metadata": dict(memory.extra_metadata or {}),
        "spans": [
            {
                "conversation_id": str(s.conversation_id),
                "start_message_id": str(s.start_message_id),
                "end_message_id": str(s.end_message_id),
                "span_type": s.span_type,
                "note": s.note,
                "sort_order": s.sort_order,
            }
            for s in spans
        ],
    }


def _write_version(
    db: Session,
    memory: Memory,
    *,
    actor: str,
    actor_model: str | None,
    reason: str | None,
) -> MemoryVersion:
    """把当前状态固化为新版本快照。调用方负责先改 memory 再调用。"""
    version = MemoryVersion(
        id=uuid.uuid4(),
        memory_id=memory.id,
        version_number=memory.current_version,
        snapshot=build_snapshot(memory, active_spans(db, memory.id)),
        edited_by_actor=actor,
        edited_by_model=actor_model,
        edit_reason=reason,
    )
    db.add(version)
    return version


def create_memory(
    db: Session,
    *,
    body: str,
    actor: str,
    actor_model: str | None = None,
    title: str | None = None,
    memory_type: str = "note",
    status: str = "active",
    importance: int | None = None,
    event_time_start: date | None = None,
    event_time_end: date | None = None,
    tags: list[str] | None = None,
    extra_metadata: dict | None = None,
    reason: str | None = None,
) -> Memory:
    if not body.strip():
        raise MemoryValidationError("body 不能为空")
    if memory_type not in MEMORY_TYPES:
        raise MemoryValidationError(f"未知 memory_type: {memory_type}")
    if status not in MEMORY_STATUSES - {"deleted"}:
        raise MemoryValidationError(f"非法初始 status: {status}")
    if event_time_start and event_time_end and event_time_start > event_time_end:
        raise MemoryValidationError("event_time_start 不能晚于 event_time_end")

    memory = Memory(
        id=uuid.uuid4(),
        title=title,
        body=body,
        memory_type=memory_type,
        status=status,
        importance=importance,
        event_time_start=event_time_start,
        event_time_end=event_time_end,
        tags=tags or [],
        extra_metadata=extra_metadata or {},
        current_version=1,
        created_by_actor=actor,
        created_by_model=actor_model,
    )
    db.add(memory)
    db.flush()
    _write_version(db, memory, actor=actor, actor_model=actor_model, reason=reason)
    audit_service.record(
        db,
        event_type="memory_created",
        actor=actor,
        actor_model=actor_model,
        target_type="memory",
        target_id=memory.id,
        detail={"version": 1},
    )
    db.commit()
    return memory


def update_memory(
    db: Session,
    memory_id: uuid.UUID,
    *,
    actor: str,
    actor_model: str | None = None,
    reason: str | None = None,
    **changes,
) -> Memory:
    memory = _get(db, memory_id)
    if memory.status == "deleted":
        raise MemoryValidationError("已删除的 memory 不能编辑，请先 restore")

    allowed = {
        "title",
        "body",
        "memory_type",
        "status",
        "importance",
        "event_time_start",
        "event_time_end",
        "tags",
        "extra_metadata",
    }
    unknown = set(changes) - allowed
    if unknown:
        raise MemoryValidationError(f"不允许修改的字段: {sorted(unknown)}")
    if "body" in changes and not str(changes["body"]).strip():
        raise MemoryValidationError("body 不能为空")
    if "memory_type" in changes and changes["memory_type"] not in MEMORY_TYPES:
        raise MemoryValidationError(f"未知 memory_type: {changes['memory_type']}")
    if "status" in changes and changes["status"] not in MEMORY_STATUSES - {"deleted"}:
        raise MemoryValidationError(f"非法 status: {changes['status']}")

    changed_fields = []
    for field, value in changes.items():
        if value is not None or field in ("title", "importance"):
            if getattr(memory, field) != value:
                changed_fields.append(field)
                setattr(memory, field, value)

    new_start = memory.event_time_start
    new_end = memory.event_time_end
    if new_start and new_end and new_start > new_end:
        raise MemoryValidationError("event_time_start 不能晚于 event_time_end")

    if not changed_fields:
        return memory  # 无实际变化不产生新版本

    memory.current_version += 1
    memory.updated_at = datetime.now(UTC)
    _write_version(db, memory, actor=actor, actor_model=actor_model, reason=reason)
    audit_service.record(
        db,
        event_type="memory_updated",
        actor=actor,
        actor_model=actor_model,
        target_type="memory",
        target_id=memory.id,
        detail={"version": memory.current_version, "changed_fields": changed_fields},
    )
    db.commit()
    return memory


def bump_version_for_span_change(
    db: Session,
    memory: Memory,
    *,
    actor: str,
    actor_model: str | None,
    reason: str | None,
    event_type: str,
    span_id: uuid.UUID,
) -> None:
    """span 增删共享的版本+审计逻辑（由 span_service 调用）。"""
    memory.current_version += 1
    memory.updated_at = datetime.now(UTC)
    _write_version(db, memory, actor=actor, actor_model=actor_model, reason=reason)
    audit_service.record(
        db,
        event_type=event_type,
        actor=actor,
        actor_model=actor_model,
        target_type="memory",
        target_id=memory.id,
        detail={"version": memory.current_version, "span_id": str(span_id)},
    )


def soft_delete_memory(
    db: Session,
    memory_id: uuid.UUID,
    *,
    actor: str,
    actor_model: str | None = None,
    reason: str | None = None,
) -> Memory:
    memory = _get(db, memory_id)
    if memory.status == "deleted":
        return memory
    memory.status = "deleted"
    memory.deleted_at = datetime.now(UTC)
    memory.current_version += 1
    memory.updated_at = datetime.now(UTC)
    _write_version(db, memory, actor=actor, actor_model=actor_model, reason=reason)
    audit_service.record(
        db,
        event_type="memory_deleted",
        actor=actor,
        actor_model=actor_model,
        target_type="memory",
        target_id=memory.id,
        detail={"version": memory.current_version},
    )
    db.commit()
    return memory


def restore_version(
    db: Session,
    memory_id: uuid.UUID,
    version_number: int,
    *,
    actor: str,
    actor_model: str | None = None,
    reason: str | None = None,
) -> Memory:
    """恢复 = 用旧快照内容追加一个新版本。历史永不被改写。"""
    memory = _get(db, memory_id)
    version = db.scalar(
        select(MemoryVersion).where(
            MemoryVersion.memory_id == memory_id,
            MemoryVersion.version_number == version_number,
        )
    )
    if version is None:
        raise MemoryNotFound(f"版本 v{version_number} 不存在")

    snap = version.snapshot
    memory.title = snap["title"]
    memory.body = snap["body"]
    memory.memory_type = snap["memory_type"]
    memory.status = snap["status"]
    memory.importance = snap["importance"]
    memory.event_time_start = (
        date.fromisoformat(snap["event_time_start"]) if snap["event_time_start"] else None
    )
    memory.event_time_end = (
        date.fromisoformat(snap["event_time_end"]) if snap["event_time_end"] else None
    )
    memory.tags = list(snap["tags"])
    memory.extra_metadata = dict(snap["extra_metadata"])
    memory.deleted_at = None if memory.status != "deleted" else memory.deleted_at

    # spans 对账：软移除当前生效 spans，按快照重建（新行，旧行留痕）
    now = datetime.now(UTC)
    for span in active_spans(db, memory.id):
        span.removed_at = now
        span.removed_by_actor = actor
    db.flush()
    for sp in snap["spans"]:
        db.add(
            MemorySourceSpan(
                id=uuid.uuid4(),
                memory_id=memory.id,
                conversation_id=uuid.UUID(sp["conversation_id"]),
                start_message_id=uuid.UUID(sp["start_message_id"]),
                end_message_id=uuid.UUID(sp["end_message_id"]),
                span_type=sp["span_type"],
                note=sp["note"],
                sort_order=sp["sort_order"],
                created_by_actor=actor,
                created_by_model=actor_model,
            )
        )
    db.flush()  # 新 spans 必须先落库，版本快照查询才能看到

    memory.current_version += 1
    memory.updated_at = now
    _write_version(db, memory, actor=actor, actor_model=actor_model, reason=reason)
    audit_service.record(
        db,
        event_type="version_restored",
        actor=actor,
        actor_model=actor_model,
        target_type="memory",
        target_id=memory.id,
        detail={
            "version": memory.current_version,
            "restored_from": version_number,
        },
    )
    db.commit()
    return memory


def list_versions(db: Session, memory_id: uuid.UUID) -> list[MemoryVersion]:
    _get(db, memory_id)
    return list(
        db.scalars(
            select(MemoryVersion)
            .where(MemoryVersion.memory_id == memory_id)
            .order_by(MemoryVersion.version_number)
        ).all()
    )
