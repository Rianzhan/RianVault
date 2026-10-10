"""遗失记忆审计（Memory Migration Audit）。

原则：候选信号 ≠ 真实记忆写入。扫描只负责筛出候选 + 提供上下文，
verdict 一律由 Owner 人工判定；系统永不自动认定。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Memory, Message, MigrationReview

SIGNALS_FILE = Path(__file__).resolve().parents[2] / "config" / "migration_signals.yaml"


def load_signals() -> tuple[list[str], int]:
    with open(SIGNALS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return list(data["signals"]), int(data.get("default_context_window", 6))


class MigrationAuditError(ValueError):
    pass


class CandidateNotFound(LookupError):
    pass


def scan(
    db: Session,
    *,
    scan_from: date,
    scan_to: date,
    source_platform: str | None = None,
) -> dict:
    """扫描 [scan_from, scan_to] 内命中信号的消息，创建/复用候选行。

    幂等：同一 signal_message_id 只有一行（unique 约束兜底）。
    返回 {created, existing, total}。
    """
    if scan_from > scan_to:
        raise MigrationAuditError("scan_from 不能晚于 scan_to")

    signals, _ = load_signals()

    stmt = select(Message).where(
        Message.content_text.is_not(None),
        Message.event_time.is_not(None),
    )
    # 时间过滤：消息 event_time 落在扫描窗口内（naive/date 比较）
    stmt = stmt.where(
        Message.event_time >= datetime.combine(scan_from, datetime.min.time(), tzinfo=UTC),
        Message.event_time < datetime.combine(scan_to, datetime.max.time(), tzinfo=UTC),
    )
    if source_platform:
        stmt = stmt.join(Message.conversation).where(
            Message.conversation.has(source_platform=source_platform)
        )

    created = 0
    existing = 0
    for msg in db.scalars(stmt):
        text = msg.content_text or ""
        hit = next((s for s in signals if s.lower() in text.lower()), None)
        if hit is None:
            continue
        row = db.scalar(select(MigrationReview).where(MigrationReview.signal_message_id == msg.id))
        if row is not None:
            existing += 1
            continue
        db.add(
            MigrationReview(
                id=uuid.uuid4(),
                signal_message_id=msg.id,
                scan_from=scan_from,
                scan_to=scan_to,
                matched_signal=hit,
            )
        )
        created += 1
    db.commit()
    return {"created": created, "existing": existing, "total": created + existing}


def _context_messages(db: Session, msg: Message, window: int) -> list[Message]:
    """信号消息前后各 window 条（按会话内 sort_order），含自身。"""
    lo = msg.sort_order - window
    hi = msg.sort_order + window
    return list(
        db.scalars(
            select(Message)
            .where(
                Message.conversation_id == msg.conversation_id,
                Message.sort_order >= lo,
                Message.sort_order <= hi,
            )
            .order_by(Message.sort_order)
        ).all()
    )


def list_candidates(
    db: Session,
    *,
    verdict: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """候选列表，带前后上下文（供 Owner 审阅，绝不只给一句关键词）。"""
    _, window = load_signals()
    stmt = select(MigrationReview).order_by(MigrationReview.created_at.desc())
    if verdict:
        stmt = stmt.where(MigrationReview.verdict == verdict)
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    result = []
    for row in rows:
        msg = db.get(Message, row.signal_message_id)
        if msg is None:
            continue
        ctx = _context_messages(db, msg, window)
        result.append(
            {
                "id": row.id,
                "matched_signal": row.matched_signal,
                "verdict": row.verdict,
                "signal_message": {
                    "id": msg.id,
                    "role": msg.role,
                    "content_text": msg.content_text,
                    "event_time": msg.event_time,
                    "sort_order": msg.sort_order,
                },
                "context": [
                    {
                        "id": m.id,
                        "role": m.role,
                        "content_text": m.content_text,
                        "event_time": m.event_time,
                        "sort_order": m.sort_order,
                    }
                    for m in ctx
                ],
                "context_start_message_id": row.context_start_message_id,
                "context_end_message_id": row.context_end_message_id,
                "linked_memory_id": row.linked_memory_id,
                "note": row.note,
            }
        )
    return result


def set_verdict(
    db: Session,
    review_id: uuid.UUID,
    verdict: str,
    *,
    reviewed_by: str,
    note: str | None = None,
) -> MigrationReview:
    from app.models.migration_review import VERDICTS

    row = db.get(MigrationReview, review_id)
    if row is None:
        raise CandidateNotFound("候选记录不存在")
    if verdict not in VERDICTS:
        raise MigrationAuditError(f"verdict 必须是 {sorted(VERDICTS)} 之一")
    row.verdict = verdict
    row.reviewed_by = reviewed_by
    row.reviewed_at = datetime.now(UTC)
    if note is not None:
        row.note = note
    db.commit()
    return row


def create_memory_from_candidate(
    db: Session,
    review_id: uuid.UUID,
    *,
    body: str,
    actor: str,
    actor_model: str | None = None,
    span_type: str = "evidence",
    context_start_message_id: uuid.UUID | None = None,
    context_end_message_id: uuid.UUID | None = None,
    title: str | None = None,
    memory_type: str = "note",
    event_time_start: date | None = None,
    event_time_end: date | None = None,
    tags: list[str] | None = None,
) -> tuple[Memory, MigrationReview]:
    """从候选创建 memory：span 绑定 Owner 选定的上下文范围（可以比信号句大）。

    注意默认 event_time 取信号消息的 event_time（事情发生时间），
    而不是今天——避免「2025 年发生的事被记成 2026 的记忆」。
    """
    from app.services import memory_service, span_service

    row = db.get(MigrationReview, review_id)
    if row is None:
        raise CandidateNotFound("候选记录不存在")
    if row.linked_memory_id is not None:
        raise MigrationAuditError("该候选已关联 memory，请勿重复创建")
    sig_msg = db.get(Message, row.signal_message_id)
    if sig_msg is None:
        raise CandidateNotFound("信号消息不存在")

    start_id = context_start_message_id or row.context_start_message_id or sig_msg.id
    end_id = context_end_message_id or row.context_end_message_id or sig_msg.id

    if event_time_start is None and sig_msg.event_time is not None:
        event_time_start = sig_msg.event_time.date()
        if event_time_end is None:
            event_time_end = event_time_start

    memory = memory_service.create_memory(
        db,
        body=body,
        actor=actor,
        actor_model=actor_model,
        title=title,
        memory_type=memory_type,
        event_time_start=event_time_start,
        event_time_end=event_time_end,
        tags=tags or ["migration-audit"],
        reason="migration audit: 从候选打捞",
    )
    span_service.add_span(
        db,
        memory.id,
        conversation_id=sig_msg.conversation_id,
        start_message_id=start_id,
        end_message_id=end_id,
        span_type=span_type,
        actor=actor,
        actor_model=actor_model,
        reason="migration audit: 候选上下文",
    )

    row.linked_memory_id = memory.id
    row.context_start_message_id = start_id
    row.context_end_message_id = end_id
    if row.verdict == "unreviewed":
        row.verdict = "successful_write"  # 建了 memory 即视为 Owner 确认写入
        row.reviewed_by = actor
        row.reviewed_at = datetime.now(UTC)
    db.commit()
    return memory, row
