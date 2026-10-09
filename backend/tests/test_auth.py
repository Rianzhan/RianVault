"""T4 权限矩阵测试。矩阵见 RIANVAULT_DESIGN_AUDIT.md 附 1。"""

import uuid

from conftest import ZHAN_TOKEN, read_fixture
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models import ApiToken


def _import_fixture(client: TestClient) -> tuple[dict, list[dict]]:
    resp = client.post(
        "/api/imports",
        files={"file": ("conversations.json", read_fixture("chatgpt_export_sample.json"))},
    )
    assert resp.status_code == 200, resp.text
    conv = client.get("/api/conversations").json()[0]
    msgs = client.get(f"/api/conversations/{conv['id']}/messages").json()
    return conv, msgs


def _mk_memory(client: TestClient) -> dict:
    resp = client.post("/api/memories", json={"body": "权限测试记忆"})
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestAnonymous:
    def test_health_is_public(self, anon_client: TestClient) -> None:
        assert anon_client.get("/health").status_code == 200

    def test_no_token_401_everywhere(self, anon_client: TestClient) -> None:
        assert anon_client.get("/api/conversations").status_code == 401
        assert anon_client.get("/api/memories").status_code == 401
        assert anon_client.post("/api/memories", json={"body": "x"}).status_code == 401
        assert anon_client.get("/api/imports").status_code == 401
        assert anon_client.get("/api/admin/tokens").status_code == 401

    def test_garbage_token_401(self, anon_client: TestClient) -> None:
        anon_client.headers["Authorization"] = "Bearer garbage"
        assert anon_client.get("/api/conversations").status_code == 401


class TestZhanAllowed:
    def test_read(self, client: TestClient, zhan_client: TestClient) -> None:
        conv, _ = _import_fixture(client)
        assert zhan_client.get("/api/conversations").status_code == 200
        assert zhan_client.get(f"/api/conversations/{conv['id']}").status_code == 200
        assert zhan_client.get("/api/memories").status_code == 200

    def test_create_edit_span(self, client: TestClient, zhan_client: TestClient) -> None:
        conv, msgs = _import_fixture(client)
        # create（actor 由 token 派生）
        resp = zhan_client.post(
            "/api/memories",
            json={"body": "湛创建的记忆", "actor_model": "gpt-5.6-sol"},
        )
        assert resp.status_code == 200, resp.text
        memory = resp.json()
        assert memory["created_by_actor"] == "zhan_mcp"
        assert memory["created_by_model"] == "gpt-5.6-sol"

        # edit（带版本史）
        resp = zhan_client.patch(f"/api/memories/{memory['id']}", json={"title": "湛改的"})
        assert resp.status_code == 200
        assert resp.json()["current_version"] == 2

        # add span
        resp = zhan_client.post(
            f"/api/memories/{memory['id']}/spans",
            json={
                "conversation_id": conv["id"],
                "start_message_id": msgs[0]["id"],
                "end_message_id": msgs[1]["id"],
                "span_type": "evidence",
            },
        )
        assert resp.status_code == 200, resp.text
        span = resp.json()

        # remove span（权限矩阵允许 add/remove source span）
        resp = zhan_client.request(
            "DELETE", f"/api/memories/{memory['id']}/spans/{span['id']}", json={}
        )
        assert resp.status_code == 200

        # 审计里全部记为 zhan_mcp
        events = zhan_client.get(f"/api/memories/{memory['id']}/audit").json()
        assert all(e["actor"] == "zhan_mcp" for e in events)


class TestZhanForbidden:
    def test_delete_memory_403(self, client: TestClient, zhan_client: TestClient) -> None:
        memory = _mk_memory(client)
        resp = zhan_client.request("DELETE", f"/api/memories/{memory['id']}", json={})
        assert resp.status_code == 403

    def test_restore_403(self, client: TestClient, zhan_client: TestClient) -> None:
        memory = _mk_memory(client)
        resp = zhan_client.post(f"/api/memories/{memory['id']}/restore", json={"version_number": 1})
        assert resp.status_code == 403

    def test_import_403(self, zhan_client: TestClient) -> None:
        resp = zhan_client.post(
            "/api/imports",
            files={"file": ("c.json", read_fixture("chatgpt_export_sample.json"))},
        )
        assert resp.status_code == 403
        assert zhan_client.get("/api/imports").status_code == 403

    def test_token_admin_403(self, zhan_client: TestClient) -> None:
        assert zhan_client.get("/api/admin/tokens").status_code == 403
        resp = zhan_client.post("/api/admin/tokens", json={"name": "x", "role": "owner"})
        assert resp.status_code == 403
        resp = zhan_client.post(f"/api/admin/tokens/{uuid.uuid4()}/revoke")
        assert resp.status_code == 403


class TestOwnerAdmin:
    def test_create_list_revoke_token(self, client: TestClient, db_session: Session) -> None:
        resp = client.post("/api/admin/tokens", json={"name": "新湛", "role": "zhan_mcp"})
        assert resp.status_code == 200, resp.text
        created = resp.json()
        assert created["token"].startswith("rv_")  # 明文仅这一次
        assert created["role"] == "zhan_mcp"

        listing = client.get("/api/admin/tokens").json()
        assert any(t["id"] == created["id"] for t in listing)
        assert all(
            "token" not in t or t["token"] is None for t in listing if t["id"] != created["id"]
        )

        # 新 token 可用
        row = db_session.scalar(select(ApiToken).where(ApiToken.id == uuid.UUID(created["id"])))
        assert row.token_hash == hash_token(created["token"])
        assert created["token"] not in str(row.token_hash)

        # 吊销后立即 401
        resp = client.post(f"/api/admin/tokens/{created['id']}/revoke")
        assert resp.status_code == 200
        assert resp.json()["revoked_at"] is not None

    def test_bad_role_400(self, client: TestClient) -> None:
        resp = client.post("/api/admin/tokens", json={"name": "x", "role": "superadmin"})
        assert resp.status_code == 400

    def test_last_used_at_updated(self, client: TestClient, db_session: Session) -> None:
        client.get("/api/conversations")
        zhan_row = db_session.scalar(
            select(ApiToken).where(ApiToken.token_hash == hash_token(ZHAN_TOKEN))
        )
        assert zhan_row.last_used_at is None  # zhan 还没用过
        owner_row = db_session.scalar(select(ApiToken).where(ApiToken.name == "test-owner"))
        assert owner_row.last_used_at is not None
