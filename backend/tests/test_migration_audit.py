"""T5 遗失记忆审计测试。"""

import pytest
from conftest import read_fixture
from fastapi.testclient import TestClient

from app.services import migration_audit_service as svc


@pytest.fixture()
def imported_signals(client: TestClient) -> dict:
    resp = client.post(
        "/api/imports",
        files={
            "file": ("migration_signals_chat.json", read_fixture("migration_signals_chat.json"))
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["import_"]["status"] == "completed"
    return resp.json()["import_"]["stats"]


class TestScan:
    def test_scan_finds_candidates_not_auto_confirm(
        self, client: TestClient, imported_signals: dict
    ) -> None:
        # 1782000000 ≈ 2026-06-21（UTC）；扫 2026-06-01 ~ 2026-07-31
        report = client.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": "2026-06-01", "scan_to": "2026-07-31"},
        ).json()
        assert report["created"] == 6  # 6 条消息全部命中（每条至少一个信号）
        assert report["existing"] == 0

        candidates = client.get("/api/audit/migration-candidates").json()
        assert len(candidates) == 6
        # 命中 ≠ 认定：全部默认 unreviewed
        assert all(c["verdict"] == "unreviewed" for c in candidates)
        # 上下文必须带出来（前后窗口）
        first = next(c for c in candidates if c["signal_message"].get("sort_order") == 1)
        assert len(first["context"]) >= 3
        assert first["matched_signal"] == "加入记忆库"

    def test_scan_idempotent(self, client: TestClient, imported_signals: dict) -> None:
        client.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": "2026-06-01", "scan_to": "2026-07-31"},
        )
        report = client.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": "2026-06-01", "scan_to": "2026-07-31"},
        ).json()
        assert report["created"] == 0
        assert report["existing"] == 6

    def test_scan_window_excludes_outside(self, client: TestClient, imported_signals: dict) -> None:
        report = client.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": "2025-01-01", "scan_to": "2025-12-31"},
        ).json()
        assert report["total"] == 0

    def test_scan_invalid_range_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": "2026-07-31", "scan_to": "2026-06-01"},
        )
        assert resp.status_code == 400

    def test_scan_owner_only(self, zhan_client: TestClient) -> None:
        resp = zhan_client.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": "2026-06-01", "scan_to": "2026-07-31"},
        )
        assert resp.status_code == 403


class TestVerdict:
    def test_set_verdict_persists(self, client: TestClient, imported_signals: dict) -> None:
        client.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": "2026-06-01", "scan_to": "2026-07-31"},
        )
        candidates = client.get("/api/audit/migration-candidates").json()
        # 同一消息可能命中多个信号（如"记忆空间已经满了"+"没有成功存进去"），
        # 扫描记录第一个命中信号；测试按信号消息内容定位
        target = next(
            c for c in candidates if "没有成功存进去" in c["signal_message"]["content_text"]
        )
        resp = client.post(
            f"/api/audit/migration-candidates/{target['id']}/verdict",
            json={"verdict": "failed_write", "note": "确认当时写入失败"},
        )
        assert resp.status_code == 200
        assert resp.json()["verdict"] == "failed_write"

        filtered = client.get(
            "/api/audit/migration-candidates", params={"verdict": "failed_write"}
        ).json()
        assert len(filtered) == 1

    def test_bad_verdict_400(self, client: TestClient, imported_signals: dict) -> None:
        client.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": "2026-06-01", "scan_to": "2026-07-31"},
        )
        candidates = client.get("/api/audit/migration-candidates").json()
        resp = client.post(
            f"/api/audit/migration-candidates/{candidates[0]['id']}/verdict",
            json={"verdict": "definitely_real"},
        )
        assert resp.status_code == 400


class TestCreateMemoryFromCandidate:
    def test_create_binds_selected_context(
        self, client: TestClient, imported_signals: dict
    ) -> None:
        client.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": "2026-06-01", "scan_to": "2026-07-31"},
        )
        candidates = client.get("/api/audit/migration-candidates").json()
        by_signal = next(c for c in candidates if c["matched_signal"] == "加入记忆库")

        # Owner 选定更大上下文：n1(信号句) 前后到 n4（信号句是 sort_order=1，选 0..4）
        ctx_ids = [m["id"] for m in by_signal["context"]]
        assert len(ctx_ids) >= 3

        resp = client.post(
            f"/api/audit/migration-candidates/{by_signal['id']}/create-memory",
            json={
                "body": (
                    "6 月末曾请 4o 把「这件事」加入记忆库，当时报记忆空间满、写入失败，重试后成功。"
                ),
                "memory_type": "event",
                "title": "记忆库写入故障（2026-06）",
                "span_type": "evidence",
                "context_start_message_id": ctx_ids[0],
                "context_end_message_id": ctx_ids[4] if len(ctx_ids) > 4 else ctx_ids[-1],
                "actor_model": "manual_by_Owner",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["verdict"] == "successful_write"
        memory_id = data["memory_id"]

        detail = client.get(f"/api/memories/{memory_id}").json()
        assert len(detail["spans"]) == 1
        span = detail["spans"][0]
        assert span["span_type"] == "evidence"
        assert str(span["start_message_id"]) == ctx_ids[0]
        # event_time 默认取信号消息的发生时间（2026-06），不是今天
        assert detail["memory"]["event_time_start"] == "2026-06-21"
        assert "migration-audit" in detail["memory"]["tags"]

        # 候选已关联，重复创建被拒
        resp = client.post(
            f"/api/audit/migration-candidates/{by_signal['id']}/create-memory",
            json={"body": "重复创建应失败"},
        )
        assert resp.status_code == 400

    def test_zhan_can_create_from_candidate(
        self, client: TestClient, zhan_client: TestClient, imported_signals: dict
    ) -> None:
        client.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": "2026-06-01", "scan_to": "2026-07-31"},
        )
        candidates = client.get("/api/audit/migration-candidates").json()
        resp = zhan_client.post(
            f"/api/audit/migration-candidates/{candidates[0]['id']}/create-memory",
            json={"body": "湛打捞的记忆", "actor_model": "gpt-5.6-sol"},
        )
        assert resp.status_code == 200, resp.text
        detail = client.get(f"/api/memories/{resp.json()['memory_id']}").json()
        assert detail["memory"]["created_by_actor"] == "zhan_mcp"


class TestSignalConfig:
    def test_signals_file_complete(self) -> None:
        signals, window = svc.load_signals()
        assert len(signals) == 31  # 13 原始 + 18 补充（Owner 2026-10-09 确认）
        assert window >= 4
        # 关键信号抽查
        assert "Model set context updated." in signals
        assert "memory full" in signals
        assert "没有写进去" in signals
