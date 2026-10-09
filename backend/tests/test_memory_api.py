"""T3 API 测试：从导入到建记忆、编辑留版本、span 管理、恢复的完整链路。"""

import uuid

from conftest import read_fixture
from fastapi.testclient import TestClient


def _import_fixture(client: TestClient) -> tuple[dict, list[dict]]:
    client.post(
        "/api/imports",
        files={"file": ("conversations.json", read_fixture("chatgpt_export_sample.json"))},
    )
    conv = client.get("/api/conversations").json()[0]
    msgs = client.get(f"/api/conversations/{conv['id']}/messages").json()
    return conv, msgs


def _create_memory(client: TestClient, **kw) -> dict:
    payload = {"body": "Owner偏好安静、有空间感的环境。", "memory_type": "preference"}
    payload.update(kw)
    resp = client.post("/api/memories", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestMemoryLifecycle:
    def test_full_cycle(self, client: TestClient) -> None:
        conv, msgs = _import_fixture(client)

        # 创建（带发生日期：2025 发生的事，2026 年录入）
        memory = _create_memory(
            client,
            title="居住偏好",
            event_time_start="2025-03-14",
            actor="zhan_mcp",
            actor_model="gpt-5.6-sol",
        )
        assert memory["current_version"] == 1
        assert memory["created_by_actor"] == "zhan_mcp"
        assert memory["created_by_model"] == "gpt-5.6-sol"

        # 加 evidence span（v2）
        span_resp = client.post(
            f"/api/memories/{memory['id']}/spans",
            json={
                "conversation_id": conv["id"],
                "start_message_id": msgs[0]["id"],
                "end_message_id": msgs[1]["id"],
                "span_type": "evidence",
                "actor": "zhan_mcp",
            },
        )
        assert span_resp.status_code == 200, span_resp.text
        span = span_resp.json()

        # 加 context span（v3）
        client.post(
            f"/api/memories/{memory['id']}/spans",
            json={
                "conversation_id": conv["id"],
                "start_message_id": msgs[2]["id"],
                "end_message_id": msgs[3]["id"],
                "span_type": "context",
                "actor": "owner",
            },
        )

        # 编辑正文（v4）
        patch = client.patch(
            f"/api/memories/{memory['id']}",
            json={"body": "Owner偏好安静、柔和、有空间感的家。", "actor": "owner"},
        )
        assert patch.status_code == 200
        assert patch.json()["current_version"] == 4

        # Genesis 详情：正文 + 元数据 + spans + 版本史 + 审计史
        detail = client.get(f"/api/memories/{memory['id']}").json()
        assert detail["memory"]["body"] == "Owner偏好安静、柔和、有空间感的家。"
        assert detail["memory"]["event_time_start"] == "2025-03-14"
        assert len(detail["spans"]) == 2
        assert {s["span_type"] for s in detail["spans"]} == {"evidence", "context"}
        assert len(detail["versions"]) == 4
        event_types = [e["event_type"] for e in detail["audit_events"]]
        assert event_types == [
            "memory_created",
            "span_added",
            "span_added",
            "memory_updated",
        ]
        # 版本快照含 spans（v3 快照应有 2 条 span）
        assert len(detail["versions"][2]["snapshot"]["spans"]) == 2

        # 删除一个 span（v5）
        del_resp = client.request(
            "DELETE",
            f"/api/memories/{memory['id']}/spans/{span['id']}",
            json={"actor": "owner"},
        )
        assert del_resp.status_code == 200
        detail = client.get(f"/api/memories/{memory['id']}").json()
        assert len(detail["spans"]) == 1
        assert detail["memory"]["current_version"] == 5

        # 恢复到 v3（v6 = 追加，不改写历史）
        restore = client.post(
            f"/api/memories/{memory['id']}/restore",
            json={"version_number": 3, "actor": "owner", "reason": "回滚"},
        )
        assert restore.status_code == 200
        detail = client.get(f"/api/memories/{memory['id']}").json()
        assert detail["memory"]["current_version"] == 6
        assert len(detail["versions"]) == 6
        assert len(detail["spans"]) == 2  # v3 快照的 spans 被重建

        # 软删除 → 列表默认排除
        client.request("DELETE", f"/api/memories/{memory['id']}", json={"actor": "owner"})
        listing = client.get("/api/memories").json()
        assert all(m["id"] != memory["id"] for m in listing)
        listing_all = client.get("/api/memories", params={"status": "deleted"}).json()
        assert any(m["id"] == memory["id"] for m in listing_all)

    def test_list_and_search(self, client: TestClient) -> None:
        _create_memory(client, title="目标 A", memory_type="goal")
        _create_memory(client, body="完全无关的内容", memory_type="note")
        goals = client.get("/api/memories", params={"memory_type": "goal"}).json()
        assert len(goals) == 1
        hits = client.get("/api/memories", params={"q": "无关"}).json()
        assert len(hits) == 1

    def test_validation_400(self, client: TestClient) -> None:
        resp = client.post("/api/memories", json={"body": "  "})
        assert resp.status_code == 400
        resp = client.post("/api/memories", json={"body": "x", "memory_type": "bogus"})
        assert resp.status_code == 400

    def test_span_400_and_404(self, client: TestClient) -> None:
        conv, msgs = _import_fixture(client)
        memory = _create_memory(client)
        # 反向范围
        resp = client.post(
            f"/api/memories/{memory['id']}/spans",
            json={
                "conversation_id": conv["id"],
                "start_message_id": msgs[3]["id"],
                "end_message_id": msgs[0]["id"],
                "span_type": "evidence",
            },
        )
        assert resp.status_code == 400
        # 不存在的 memory / span
        resp = client.get(f"/api/memories/{uuid.uuid4()}")
        assert resp.status_code == 404
        resp = client.request(
            "DELETE",
            f"/api/memories/{memory['id']}/spans/{uuid.uuid4()}",
            json={"actor": "owner"},
        )
        assert resp.status_code == 404
        # 不存在版本
        resp = client.post(
            f"/api/memories/{memory['id']}/restore",
            json={"version_number": 42},
        )
        assert resp.status_code == 404
