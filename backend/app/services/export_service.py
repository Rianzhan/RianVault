"""Portable Export：把整个档案馆打包成一个可人工阅读、可程序恢复的 zip。

布局见 RIANVAULT_DESIGN_AUDIT.md 附 2。要点：
- data/*.jsonl 是全量表数据（权威、可恢复）；markdown/ 是给人读的。
- 向量不导出：Qdrant 索引可再生（rebuild_qdrant.py）。
- 所有文件带 sha256，manifest 统一登记 —— 恢复前先校验。
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AuditEvent,
    ChunkIndex,
    Conversation,
    Import,
    Memory,
    MemorySourceSpan,
    MemoryVersion,
    Message,
)
from app.services import audit_service

FORMAT_VERSION = "rianvault-export-v1"
APP_VERSION = "0.1.0"

_FILENAME_SAFE = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_ZIP_NAME = re.compile(r"^rianvault-export-\d{8}-\d{6}\.zip$")


def safe_filename(name: str, max_len: int = 60) -> str:
    cleaned = _FILENAME_SAFE.sub("_", name).strip().strip(".") or "untitled"
    return cleaned[:max_len]


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"无法序列化: {type(obj)}")


def _model_columns(model: type) -> list[str]:
    return [c.key for c in inspect(model).mapper.column_attrs]


def _row_dict(row: Any, columns: list[str]) -> dict:
    return {col: getattr(row, col) for col in columns}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=_json_default) + "\n")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ExportReport:
    export_id: str
    zip_path: Path
    sha256: str
    counts: dict
    files: int


def build_export(
    db: Session,
    *,
    actor: str = "owner",
    actor_model: str | None = None,
    out_dir: Path | None = None,
) -> ExportReport:
    """导出全部数据到临时目录并打包 zip；产出后清理临时目录。"""
    settings = get_settings()
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_dir or settings.export_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # 中间产物一律放系统临时目录：exports/ 里只会出现最终 zip，
    # 不碰用户可见目录里的任何其他文件（也更少触发删除）。
    work = Path(tempfile.mkdtemp(prefix=f"rianvault-export-{stamp}-"))
    data_dir = work / "data"
    md_memories = work / "markdown" / "memories"
    md_conversations = work / "markdown" / "conversations"
    for d in (data_dir, md_memories, md_conversations):
        d.mkdir(parents=True, exist_ok=True)

    # ---------- 表数据（jsonl） ----------
    jobs: list[tuple[str, type, list[str]]] = [
        ("conversations", Conversation, []),
        ("messages", Message, []),
        ("memories", Memory, []),
        ("memory_versions", MemoryVersion, []),
        ("memory_source_spans", MemorySourceSpan, []),
        ("audit_events", AuditEvent, []),
        ("imports", Import, []),
        # 索引状态（不含向量）：恢复后 know「哪些已索引」，向量仍可再生
        ("chunks", ChunkIndex, []),
    ]
    order_by_map: dict[str, Any] = {
        "messages": Message.conversation_id,
        "memory_versions": MemoryVersion.memory_id,
        "memory_source_spans": MemorySourceSpan.memory_id,
        "audit_events": AuditEvent.created_at,
        "chunks": ChunkIndex.message_id,
    }
    counts: dict[str, int] = {}
    for name, model, _ in jobs:
        columns = _model_columns(model)
        stmt = select(model)
        if name in order_by_map:
            stmt = stmt.order_by(order_by_map[name])
        rows = [_row_dict(r, columns) for r in db.scalars(stmt).all()]
        counts[name] = len(rows)
        _write_jsonl(data_dir / f"{name}.jsonl", rows)

    # ---------- 人类可读 markdown ----------
    # markdown 计数单独放：manifest.counts 只登记"可恢复的表"，
    # 否则恢复对账会把 markdown 文件数当成缺失表数据而误报不一致。
    markdown_counts: dict[str, int] = {}
    _write_memory_markdown(db, md_memories, markdown_counts)
    _write_conversation_markdown(db, md_conversations, markdown_counts)

    # ---------- manifest + checksums ----------
    files: dict[str, str] = {}
    for path in sorted(work.rglob("*")):
        if path.is_file():
            rel = path.relative_to(work).as_posix()
            files[rel] = _sha256_file(path)

    manifest = {
        "format_version": FORMAT_VERSION,
        "app_version": APP_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "exported_by": {"actor": actor, "model": actor_model},
        "counts": counts,
        "markdown_counts": markdown_counts,
        "files": files,
        "notes": [
            "向量不导出（可用 rebuild_qdrant.py 从原文重算）",
            "chunks.jsonl 只记录索引状态，不含向量",
        ],
    }
    manifest_path = work / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )

    checksum_lines = []
    for rel in sorted(files):
        checksum_lines.append(f"{files[rel]}  {rel}")
    (work / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    # ---------- zip ----------
    zip_path = out_dir / f"rianvault-export-{stamp}.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(work.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(work).as_posix())
    finally:
        shutil.rmtree(work, ignore_errors=True)

    audit_service.record(
        db,
        event_type="export_created",
        actor=actor,
        actor_model=actor_model,
        target_type="export",
        target_id=uuid.uuid5(uuid.NAMESPACE_URL, f"rianvault:export:{zip_path.name}"),
        # target_id 在表里是 NOT NULL：用 export_id 推导一个稳定 uuid 作为句柄
        detail={"export_id": zip_path.name, "counts": counts},  # 不记正文
    )
    db.commit()

    return ExportReport(
        export_id=zip_path.name,
        zip_path=zip_path,
        sha256=_sha256_file(zip_path),
        counts=counts,
        files=len(files) + 2,  # manifest + checksums
    )


def list_exports(out_dir: Path | None = None) -> list[dict]:
    out_dir = Path(out_dir or get_settings().export_dir)
    if not out_dir.exists():
        return []
    items = []
    for path in sorted(out_dir.glob("rianvault-export-*.zip"), reverse=True):
        stat = path.stat()
        items.append(
            {
                "export_id": path.name,
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            }
        )
    return items


def resolve_export_path(export_id: str, out_dir: Path | None = None) -> Path:
    """按文件名解析 zip —— 拒绝路径穿越，文件不存在就报 404。"""
    if not _ZIP_NAME.match(export_id):
        raise ValueError("export_id 不合法")
    out_dir = Path(out_dir or get_settings().export_dir).resolve()
    path = (out_dir / export_id).resolve()
    if path.parent != out_dir or not path.is_file():
        raise FileNotFoundError(export_id)
    return path


def _write_memory_markdown(db: Session, out: Path, counts: dict) -> None:
    memories = list(db.scalars(select(Memory).order_by(Memory.created_at)).all())
    counts["markdown_memories"] = len(memories)
    for mem in memories:
        spans = list(
            db.scalars(
                select(MemorySourceSpan)
                .where(MemorySourceSpan.memory_id == mem.id)
                .order_by(MemorySourceSpan.sort_order)
            ).all()
        )
        fm = {
            "title": mem.title or "(无标题)",
            "memory_type": mem.memory_type,
            "status": mem.status,
            "importance": mem.importance,
            "event_time_start": mem.event_time_start,
            "event_time_end": mem.event_time_end,
            "created_by_actor": mem.created_by_actor,
            "created_by_model": mem.created_by_model,
            "current_version": mem.current_version,
            "tags": mem.tags or [],
        }
        lines = ["---"]
        for key, value in fm.items():
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False, default=_json_default)}")
        lines.append("---")
        lines.append("")
        lines.append(mem.body or "")
        lines.append("")
        lines.append("## 来源")
        for span in spans:
            conv = db.get(Conversation, span.conversation_id)
            if conv is None:
                continue
            start_ok = db.scalar(
                select(Message.sort_order).where(Message.id == span.start_message_id)
            )
            end_ok = db.scalar(select(Message.sort_order).where(Message.id == span.end_message_id))
            msgs = list(
                db.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == span.conversation_id,
                        Message.sort_order >= (start_ok or 0),
                        Message.sort_order <= (end_ok or 0),
                    )
                    .order_by(Message.sort_order)
                ).all()
            )
            lines.append("")
            lines.append(
                f"- [{span.span_type}] 会话「{conv.title or conv.source_conversation_id or '?'}」"
                f"（{conv.source_platform}）"
            )
            for m in msgs:
                if m.content_text:
                    lines.append(f"  > {m.role}: {m.content_text}")
        filename = safe_filename(f"{mem.id}-{mem.title or 'untitled'}") + ".md"
        (out / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_conversation_markdown(db: Session, out: Path, counts: dict) -> None:
    conversations = list(db.scalars(select(Conversation).order_by(Conversation.created_at)).all())
    counts["markdown_conversations"] = len(conversations)
    for conv in conversations:
        lines = [
            f"# {conv.title or conv.source_conversation_id or '(无标题)'}",
            "",
            f"- 平台: {conv.source_platform}",
            f"- 源会话 ID: {conv.source_conversation_id or '?'}",
            f"- 开始时间: {conv.started_at.isoformat() if conv.started_at else '?'}",
            "",
        ]
        msgs = list(
            db.scalars(
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.sort_order)
            ).all()
        )
        for m in msgs:
            if not m.content_text:
                continue
            stamp = m.event_time.isoformat() if m.event_time else "?"
            lines.append(f"## {m.role} · {stamp}")
            lines.append("")
            lines.append(m.content_text)
            lines.append("")
        filename = safe_filename(f"{conv.id}-{conv.title or 'conversation'}") + ".md"
        (out / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")
