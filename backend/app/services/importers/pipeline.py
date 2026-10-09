"""导入管线：幂等、对账、绝不静默丢数据。

不变式：messages_parsed == imported + duplicates + quarantined，不满足即 failed。
任何异常都会让 import 置为 failed 并记录 error——禁止吞掉异常假装成功。
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Import, ImportQuarantine, Message
from app.services.importers import ADAPTERS
from app.services.importers.base import CanonicalConversation, ImporterAdapter


class ImportRejected(Exception):
    """文件无法识别或违反导入限制（在创建 import 记录之前）。"""


@dataclass
class ImportOutcome:
    import_: Import
    already_imported: bool


def _detect_adapter(data: bytes, filename: str, source_type: str | None) -> ImporterAdapter:
    if source_type:
        for adapter in ADAPTERS:
            if adapter.name == source_type:
                return adapter
        raise ImportRejected(f"未知的 source_type: {source_type!r}")
    for adapter in ADAPTERS:
        if adapter.detect(data, filename):
            return adapter
    raise ImportRejected("无法识别的导入格式（没有 adapter 接受该文件）")


def _get_or_create_conversation(
    db: Session, imp: Import, conv: CanonicalConversation, counts: dict
) -> Conversation:
    row = None
    if conv.source_conversation_id:
        row = db.scalar(
            select(Conversation).where(
                Conversation.source_platform == conv.source_platform,
                Conversation.source_conversation_id == conv.source_conversation_id,
            )
        )
    elif conv.dedup_hash:
        row = db.scalar(select(Conversation).where(Conversation.dedup_hash == conv.dedup_hash))
    if row is not None:
        # 会话已存在（例如再次导出了仍在增长的会话）：复用，消息级去重兜底
        return row
    row = Conversation(
        id=uuid.uuid4(),
        source_platform=conv.source_platform,
        source_conversation_id=conv.source_conversation_id,
        title=conv.title,
        import_id=imp.id,
        raw_metadata=conv.raw_metadata,
        dedup_hash=conv.dedup_hash,
    )
    db.add(row)
    db.flush()  # 分配 id 供消息引用；唯一约束冲突会在此抛出
    counts["conversations_new"] += 1
    return row


def _import_messages(
    db: Session,
    imp: Import,
    conv: CanonicalConversation,
    conv_row: Conversation,
    counts: dict,
) -> None:
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    min_event_time = None

    for msg in conv.messages:
        if msg.raw_metadata.get("placeholder"):
            # 占位节点（ChatGPT 树根等）：结构性跳过，不算解析到的消息
            continue
        counts["messages_parsed"] += 1

        if msg.error is not None:
            db.add(
                ImportQuarantine(
                    id=uuid.uuid4(),
                    import_id=imp.id,
                    raw_payload=msg.error_raw or {"error": msg.error},
                    reason=msg.error,
                )
            )
            counts["quarantined"] += 1
            continue

        # 文件内自重复（同一会话内相同 id/哈希出现两次）
        if msg.source_message_id and msg.source_message_id in seen_ids:
            counts["duplicates"] += 1
            continue
        if msg.dedup_hash in seen_hashes:
            counts["duplicates"] += 1
            continue

        if msg.source_message_id:
            dup = db.scalar(
                select(Message.id).where(
                    Message.conversation_id == conv_row.id,
                    Message.source_message_id == msg.source_message_id,
                )
            )
        else:
            dup = db.scalar(
                select(Message.id).where(
                    Message.conversation_id == conv_row.id,
                    Message.dedup_hash == msg.dedup_hash,
                )
            )
        if dup is not None:
            counts["duplicates"] += 1
            continue

        db.add(
            Message(
                id=uuid.uuid4(),
                conversation_id=conv_row.id,
                source_message_id=msg.source_message_id,
                parent_source_message_id=msg.parent_source_message_id,
                sort_order=msg.sort_order,
                role=msg.role,
                content_text=msg.content_text,
                content_kind=msg.content_kind,
                content_raw=msg.content_raw,
                event_time=msg.event_time,
                event_time_raw=msg.event_time_raw,
                source_model=msg.source_model,
                source_model_note=msg.source_model_note,
                model_label_source=msg.model_label_source,
                import_id=imp.id,
                raw_metadata=msg.raw_metadata,
                dedup_hash=msg.dedup_hash,
            )
        )
        if msg.source_message_id:
            seen_ids.add(msg.source_message_id)
        seen_hashes.add(msg.dedup_hash)
        counts["imported"] += 1
        if msg.event_time and (min_event_time is None or msg.event_time < min_event_time):
            min_event_time = msg.event_time

    if conv_row.started_at is None and min_event_time is not None:
        conv_row.started_at = min_event_time


def run_import(
    db: Session,
    data: bytes,
    filename: str,
    source_type: str | None = None,
    max_file_mb: int = 512,
) -> ImportOutcome:
    if len(data) > max_file_mb * 1024 * 1024:
        raise ImportRejected(f"文件超过大小上限 {max_file_mb}MB")

    checksum = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(Import).where(Import.checksum_sha256 == checksum))
    if existing is not None and existing.status == "completed":
        return ImportOutcome(import_=existing, already_imported=True)

    adapter = _detect_adapter(data, filename, source_type)

    if existing is not None:
        # 同一文件上次 failed：复用台账行重试（checksum 唯一约束），
        # 清掉上次尝试的诊断数据，台账反映最新一次尝试
        imp = existing
        db.query(ImportQuarantine).where(ImportQuarantine.import_id == imp.id).delete()
        imp.source_type = adapter.name
        imp.original_filename = filename
        imp.file_size_bytes = len(data)
        imp.adapter_version = adapter.version
        imp.status = "running"
        imp.stats = {}
        imp.warnings = []
        imp.error = None
        imp.finished_at = None
    else:
        imp = Import(
            id=uuid.uuid4(),
            source_type=adapter.name,
            original_filename=filename,
            checksum_sha256=checksum,
            file_size_bytes=len(data),
            adapter_version=adapter.version,
            status="running",
            stats={},
            warnings=[],
        )
        db.add(imp)
    db.commit()

    counts = {
        "conversations_parsed": 0,
        "conversations_new": 0,
        "messages_parsed": 0,
        "imported": 0,
        "duplicates": 0,
        "quarantined": 0,
    }
    warnings: list[str] = []

    try:
        for conv in adapter.parse(data):
            counts["conversations_parsed"] += 1
            warnings.extend(conv.warnings)
            conv_row = _get_or_create_conversation(db, imp, conv, counts)
            _import_messages(db, imp, conv, conv_row, counts)
            db.commit()  # 每个会话一个事务

        if (
            counts["messages_parsed"]
            != counts["imported"] + counts["duplicates"] + counts["quarantined"]
        ):
            raise RuntimeError(f"导入对账不平衡: {counts}")
        imp.status = "completed"
    except Exception as e:  # noqa: BLE001  # 导入失败屏障：任何异常都必须让 import 置 failed，绝不假装成功
        db.rollback()
        imp.status = "failed"
        imp.error = f"{type(e).__name__}: {e}"

    imp.stats = counts
    imp.warnings = warnings[:1000]  # 防爆：最多保留 1000 条 warning
    imp.finished_at = datetime.now(UTC)
    db.commit()
    return ImportOutcome(import_=imp, already_imported=False)
