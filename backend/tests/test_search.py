"""检索集成测试：真实 Qdrant（本地文件模式）+ 真实 SQL + 测试替身 embedding。

说明：embedding 用 tests/embedding_double.py 的字符袋替身（零依赖、确定性），
因此本文件验证的是**链路正确性**（切分→入库→回查→过滤→排序→权限），
不验证语义质量；语义质量由真机 bge-m3 e2e 负责。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from embedding_double import CharBagEmbeddingProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ChunkIndex
from app.services import index_service, search_service


@pytest.fixture()
def qdrant_tmp(tmp_path, monkeypatch) -> Iterator[str]:
    """把 Qdrant 指到临时目录，避免污染开发数据。"""
    path = tmp_path / "qdrant"
    monkeypatch.setenv("QDRANT_MODE", "local")
    monkeypatch.setenv("QDRANT_PATH", str(path))
    get_settings.cache_clear()
    yield str(path)
    get_settings.cache_clear()


@pytest.fixture()
def indexed(client: TestClient, db_session: Session, qdrant_tmp: str) -> dict:
    with open("tests/fixtures/chatgpt_export_sample.json", "rb") as f:
        r = client.post("/api/imports", files={"file": ("conversations.json", f)})
    assert r.status_code == 200, r.text
    stats = index_service.index_messages(db_session, provider=CharBagEmbeddingProvider())
    return stats


def test_index_creates_chunks(indexed: dict) -> None:
    assert indexed["chunks"] >= 1
    assert indexed["messages"] >= 1
    assert indexed["model"].startswith("test-charbag")


def test_index_is_idempotent(indexed: dict, db_session: Session) -> None:
    """第二次增量索引不应重复写入（同一个 uuid5 point id）。"""
    again = index_service.index_messages(db_session, provider=CharBagEmbeddingProvider())
    assert again["upserted"] == 0
    assert again["messages"] == 0


def test_model_change_forces_reindex(indexed: dict, db_session: Session) -> None:
    new_provider = CharBagEmbeddingProvider(model_name="test-charbag-v2")
    assert new_provider.model_name != indexed["model"]
    stats = index_service.index_messages(db_session, provider=new_provider)
    assert stats["upserted"] >= 1
    models = {row[0] for row in db_session.execute(select(ChunkIndex.embedding_model))}
    assert models == {new_provider.model_name}


def test_keyword_search_hits_original_text(client: TestClient, indexed: dict) -> None:
    r = client.post("/api/search", json={"query": "追溯", "mode": "keyword"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 1
    assert any("追溯" in h["content_text"] for h in body["hits"])
    assert all(h["match_types"] == ["keyword"] for h in body["hits"])


def test_semantic_search_returns_text_from_postgres(db_session: Session, indexed: dict) -> None:
    hits = search_service.semantic_search(
        db_session, "追溯 来源", provider=CharBagEmbeddingProvider()
    )
    assert hits
    top = hits[0]
    assert top.content_text.strip()
    assert top.match_types == ["semantic"]
    assert 0.0 < top.score <= 1.0


def test_semantic_search_respects_filters(db_session: Session, indexed: dict) -> None:
    hits = search_service.semantic_search(
        db_session,
        "安静",
        provider=CharBagEmbeddingProvider(),
        filters=search_service.Filters(source_platform="不存在的平台"),
    )
    assert hits == []


def test_hybrid_merges_modes(
    client: TestClient, db_session: Session, indexed: dict, monkeypatch
) -> None:
    double = CharBagEmbeddingProvider()
    monkeypatch.setattr(search_service, "get_embedding_provider", lambda *a, **kw: double)
    r = client.post("/api/search", json={"query": "追溯", "mode": "hybrid"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 1
    assert any("semantic" in h["match_types"] for h in body["hits"])


def test_empty_query_returns_nothing(client: TestClient, indexed: dict) -> None:
    r = client.post("/api/search", json={"query": "   ", "mode": "hybrid"})
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_invalid_mode_is_rejected(client: TestClient, indexed: dict) -> None:
    r = client.post("/api/search", json={"query": "x", "mode": "magic"})
    assert r.status_code == 422


def test_search_requires_token(anon_client: TestClient, indexed: dict) -> None:
    assert anon_client.post("/api/search", json={"query": "追溯"}).status_code == 401


def test_zhan_can_search(zhan_client: TestClient, indexed: dict) -> None:
    r = zhan_client.post("/api/search", json={"query": "追溯", "mode": "keyword"})
    assert r.status_code == 200


def test_zhan_cannot_rebuild_index(zhan_client: TestClient, indexed: dict) -> None:
    r = zhan_client.post("/api/index/build", json={"rebuild": True})
    assert r.status_code == 403


def test_index_status_reports_models(client: TestClient, indexed: dict) -> None:
    r = client.get("/api/index/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_chunks"] >= 1
    assert body["collection"]
