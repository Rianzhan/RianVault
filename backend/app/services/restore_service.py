"""从 Portable Export 的 zip 重建数据库。

原则：
- 只吃 data/*.jsonl，按主键原样写回（保留 uuid，memory 版本史与 span 才能对得上）。
- 先校验 manifest 与 checksums.sha256；校验不过就拒绝恢复（不静默继续）。
- 幂等：同一份 zip 反复恢复不会产生重复行（按 id 跳过已存在的）。
- 向量不恢复：恢复后用 rebuild_qdrant.py 重算（索引可再生）。
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
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

SUPPORTED_FORMATS = {"rianvault-export-v1"}
# 写入顺序：外键依赖（conversations/messages 先于 spans）
RESTORE_ORDER = (
    ("imports", Import),
    ("conversations", Conversation),
    ("messages", Message),
    ("memories", Memory),
    ("memory_versions", MemoryVersion),
    ("memory_source_spans", MemorySourceSpan),
    ("audit_events", AuditEvent),
    ("chunks", ChunkIndex),
)
DATE_FIELDS = {"event_time_start", "event_time_end"}
DATETIME_HINTS = ("_at", "started_at", "finished_at", "event_time", "ingested_at")


class RestoreError(RuntimeError):
    pass


@dataclass
class RestoreReport:
    restored: dict[str, int]
    skipped: dict[str, int]
    manifest_counts: dict[str, int]

    def mismatches(self) -> dict[str, tuple[int, int]]:
        """{表名: (manifest 计数, 实际写入+已存在)} —— 用于对账，不允许悄悄过去。

        只比对"可恢复的表"；markdown 文件数等不参与（它们在 manifest.markdown_counts）。
        """
        out = {}
        for name, _model in RESTORE_ORDER:
            expected = self.manifest_counts.get(name, 0)
            actual = self.restored.get(name, 0) + self.skipped.get(name, 0)
            if actual != expected:
                out[name] = (expected, actual)
        return out


def _coerce(model: type, row: dict) -> dict:
    """把 JSON 里的 ISO 字符串还原成日期/时间对象。"""
    columns = {c.key: c for c in model.__table__.columns}
    data = {}
    for key, value in row.items():
        column = columns.get(key)
        if column is None or value is None:
            data[key] = value
            continue
        python_type = getattr(column.type, "python_type", None)
        if python_type is datetime and isinstance(value, str):
            data[key] = datetime.fromisoformat(value)
        elif python_type is date and isinstance(value, str):
            data[key] = date.fromisoformat(value)
        elif python_type is uuid.UUID and isinstance(value, str):
            data[key] = uuid.UUID(value)
        else:
            data[key] = value
    return data


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _verify(zip_path: Path, work: Path) -> dict:
    manifest_path = work / "manifest.json"
    if not manifest_path.is_file():
        raise RestoreError("包内缺少 manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") not in SUPPORTED_FORMATS:
        raise RestoreError(f"不支持的导出格式: {manifest.get('format_version')}")

    checksum_path = work / "checksums.sha256"
    if checksum_path.is_file():
        import hashlib

        expected: dict[str, str] = {}
        for line in checksum_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, rel = line.split("  ", 1)
            expected[rel.strip()] = digest.strip()
        for rel, digest in expected.items():
            target = work / rel
            if not target.is_file():
                raise RestoreError(f"包内缺少文件: {rel}")
            h = hashlib.sha256()
            with target.open("rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
            if h.hexdigest() != digest:
                raise RestoreError(f"校验和不符: {rel}（文件可能被改动或损坏）")
    return manifest


def restore(
    zip_path: Path,
    database_url: str,
    *,
    create_tables: bool = True,
) -> RestoreReport:
    if not Path(zip_path).is_file():
        raise RestoreError(f"找不到导出文件: {zip_path}")

    engine = create_engine(database_url)
    if create_tables:
        Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    restored: dict[str, int] = {}
    skipped: dict[str, int] = {}

    work = Path(tempfile.mkdtemp(prefix="rianvault-restore-"))
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(work)
        manifest = _verify(zip_path, work)

        with SessionLocal() as db:
            for name, model in RESTORE_ORDER:
                path = work / "data" / f"{name}.jsonl"
                rows = _read_jsonl(path) if path.is_file() else []
                restored[name] = 0
                skipped[name] = 0
                for raw in rows:
                    data = _coerce(model, raw)
                    row_id = data.get("id")
                    if row_id is not None and db.get(model, row_id) is not None:
                        skipped[name] += 1
                        continue
                    db.add(model(**data))
                    restored[name] += 1
                db.commit()
    finally:
        shutil.rmtree(work, ignore_errors=True)

    report = RestoreReport(
        restored=restored,
        skipped=skipped,
        manifest_counts={k: v for k, v in manifest.get("counts", {}).items()},
    )
    mismatches = report.mismatches()
    if mismatches:
        raise RestoreError(f"恢复计数与 manifest 不一致: {mismatches}")
    return report


def count_all(database_url: str) -> dict[str, int]:
    """恢复后的对账计数（测试与脚本共用）。"""
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)
    out = {}
    with SessionLocal() as db:
        for name, model in RESTORE_ORDER:
            out[name] = db.scalar(select(func.count(model.id))) or 0
    return out
