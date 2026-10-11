"""T7 Portable Export：结构、校验和、人类可读 markdown，以及**往返恢复**。"""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import AuditEvent, Memory, MemorySourceSpan, MemoryVersion, Message
from app.services import export_service, restore_service

EXPECTED_DATASETS = (
    "conversations",
    "messages",
    "memories",
    "memory_versions",
    "memory_source_spans",
    "audit_events",
    "imports",
    "chunks",
)


@pytest.fixture()
def export_dir(tmp_path, monkeypatch) -> Iterator[Path]:
    path = tmp_path / "exports"
    monkeypatch.setenv("EXPORT_DIR", str(path))
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


@pytest.fixture()
def seeded(client: TestClient) -> dict:
    """导入真实 fixture，并建一条带 span 的记忆（会产生版本史）。"""
    with open("tests/fixtures/chatgpt_export_sample.json", "rb") as f:
        r = client.post("/api/imports", files={"file": ("conversations.json", f)})
    assert r.status_code == 200, r.text
    conv = client.get("/api/conversations").json()[0]
    msgs = client.get(f"/api/conversations/{conv['id']}/messages").json()
    memory = client.post(
        "/api/memories",
        json={
            "title": "记忆可以追溯来源",
            "body": "Owner要求：任何记忆都必须能跳回原文。",
            "memory_type": "preference",
            "event_time_start": "2023-11-14",
            "actor_model": "gpt-5.6-sol",
        },
    ).json()
    client.post(
        f"/api/memories/{memory['id']}/spans",
        json={
            "conversation_id": conv["id"],
            "start_message_id": msgs[0]["id"],
            "end_message_id": msgs[-1]["id"],
            "span_type": "evidence",
        },
    )
    return {"conversation": conv, "messages": msgs, "memory": memory}


def _unzip(zip_path: Path, target: Path) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target)
    return target


def test_export_creates_zip_with_full_layout(
    client: TestClient, seeded: dict, export_dir: Path, tmp_path: Path
) -> None:
    r = client.post("/api/export")
    assert r.status_code == 200, r.text
    body = r.json()
    zip_path = export_dir / body["export_id"]
    assert zip_path.is_file()

    work = _unzip(zip_path, tmp_path / "unzipped")
    assert (work / "manifest.json").is_file()
    assert (work / "checksums.sha256").is_file()
    for name in EXPECTED_DATASETS:
        assert (work / "data" / f"{name}.jsonl").is_file(), name
    assert any((work / "markdown" / "memories").glob("*.md"))
    assert any((work / "markdown" / "conversations").glob("*.md"))


def test_manifest_counts_match_database(
    client: TestClient, seeded: dict, export_dir: Path, tmp_path: Path, db_session: Session
) -> None:
    body = client.post("/api/export").json()
    work = _unzip(export_dir / body["export_id"], tmp_path / "m")
    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    counts = manifest["counts"]
    assert counts["messages"] == db_session.scalar(select(func.count(Message.id)))
    assert counts["memories"] == db_session.scalar(select(func.count(Memory.id)))
    assert counts["memory_versions"] >= 2  # 创建 v1 + span 触发 v2
    assert counts["memory_source_spans"] == 1
    assert manifest["format_version"] == export_service.FORMAT_VERSION


def test_checksums_verify_every_file(
    client: TestClient, seeded: dict, export_dir: Path, tmp_path: Path
) -> None:
    body = client.post("/api/export").json()
    work = _unzip(export_dir / body["export_id"], tmp_path / "c")
    expected = {}
    for line in (work / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, rel = line.split("  ", 1)
            expected[rel.strip()] = digest.strip()
    assert expected, "checksums 为空"
    for rel, digest in expected.items():
        target = work / rel
        assert target.is_file(), rel
        h = hashlib.sha256()
        h.update(target.read_bytes())
        assert h.hexdigest() == digest, rel


def test_markdown_contains_body_and_sources(
    client: TestClient, seeded: dict, export_dir: Path, tmp_path: Path
) -> None:
    body = client.post("/api/export").json()
    work = _unzip(export_dir / body["export_id"], tmp_path / "md")

    mem_files = list((work / "markdown" / "memories").glob("*.md"))
    text = "\n".join(p.read_text(encoding="utf-8") for p in mem_files)
    assert "Owner要求：任何记忆都必须能跳回原文。" in text
    assert "evidence" in text
    assert "第一条" in text or "记忆是可以追溯来源的。" in text  # 来源原文摘录

    conv_files = list((work / "markdown" / "conversations").glob("*.md"))
    conv_text = "\n".join(p.read_text(encoding="utf-8") for p in conv_files)
    assert "你好，这是第一条。" in conv_text


def test_round_trip_restores_counts_and_fields(
    client: TestClient, seeded: dict, export_dir: Path, tmp_path: Path, db_session: Session
) -> None:
    """导出 → 全新库恢复 → 计数与关键字段一致（设计文档 T7 完成标准）。"""
    body = client.post("/api/export").json()
    zip_path = export_dir / body["export_id"]

    target_db = tmp_path / "restored.db"
    url = f"sqlite:///{target_db.as_posix()}"
    report = restore_service.restore(zip_path, url)
    assert not report.mismatches(), report.mismatches()
    assert report.restored["messages"] >= 4

    engine = create_engine(url)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Memory.id))) == db_session.scalar(
            select(func.count(Memory.id))
        )
        assert db.scalar(select(func.count(MemorySourceSpan.id))) == 1
        assert db.scalar(select(func.count(MemoryVersion.id))) == db_session.scalar(
            select(func.count(MemoryVersion.id))
        )
        memory = db.scalars(select(Memory)).first()
        assert memory.body == "Owner要求：任何记忆都必须能跳回原文。"
        assert memory.event_time_start.isoformat() == "2023-11-14"
        assert memory.current_version == 2
        event_types = {e.event_type for e in db.scalars(select(AuditEvent)).all()}
        assert "memory_created" in event_types and "span_added" in event_types
    engine.dispose()


def test_restore_is_idempotent(
    client: TestClient, seeded: dict, export_dir: Path, tmp_path: Path
) -> None:
    zip_path = export_dir / client.post("/api/export").json()["export_id"]
    url = f"sqlite:///{(tmp_path / 'r2.db').as_posix()}"
    restore_service.restore(zip_path, url)
    second = restore_service.restore(zip_path, url)
    assert all(v == 0 for v in second.restored.values())
    assert second.skipped["messages"] >= 4
    counts = restore_service.count_all(url)
    assert counts["messages"] >= 4


def test_tampered_zip_is_refused(
    client: TestClient, seeded: dict, export_dir: Path, tmp_path: Path
) -> None:
    zip_path = export_dir / client.post("/api/export").json()["export_id"]
    bad = tmp_path / "tampered.zip"
    with zipfile.ZipFile(zip_path) as src, zipfile.ZipFile(bad, "w") as dst:
        for item in src.infolist():
            payload = src.read(item.filename)
            if item.filename == "data/messages.jsonl":
                payload = payload + b'{"id":"deadbeef"}\n'
            dst.writestr(item, payload)
    with pytest.raises(restore_service.RestoreError, match=r"校验和|不一致"):
        restore_service.restore(bad, f"sqlite:///{(tmp_path / 'bad.db').as_posix()}")


def test_export_records_audit_event(
    client: TestClient, seeded: dict, export_dir: Path, db_session: Session
) -> None:
    client.post("/api/export")
    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.event_type == "export_created")
    ).all()
    assert len(events) == 1
    assert "counts" in events[0].detail
    assert not any("Owner要求" in json.dumps(events[0].detail, ensure_ascii=False) for _ in [0])


def test_export_is_owner_only(
    zhan_client: TestClient, anon_client: TestClient, seeded: dict
) -> None:
    assert zhan_client.post("/api/export").status_code == 403
    assert anon_client.post("/api/export").status_code == 401


def test_download_and_path_traversal(client: TestClient, seeded: dict, export_dir: Path) -> None:
    export_id = client.post("/api/export").json()["export_id"]
    r = client.get(f"/api/export/{export_id}/download")
    assert r.status_code == 200
    assert r.content[:2] == b"PK"
    # 穿越尝试一律拒绝（路由解码后不匹配 → 404，或名字非法 → 400）
    assert client.get("/api/export/..%2F..%2Fetc%2Fpasswd/download").status_code in (400, 404)
    assert client.get("/api/export/....//....//etc/passwd/download").status_code in (400, 404)
    assert [p.name for p in export_dir.glob("*.zip")] == [export_id]
    assert (
        client.get("/api/export/rianvault-export-20000101-000000.zip/download").status_code == 404
    )


def test_list_exports(client: TestClient, seeded: dict, export_dir: Path) -> None:
    client.post("/api/export")
    items = client.get("/api/export").json()
    assert len(items) == 1 and items[0]["size_bytes"] > 0
