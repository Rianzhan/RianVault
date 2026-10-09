"""T3/T4 端到端验证脚本：走真实 HTTP API + 真实 token，验证 memory 生命周期与权限矩阵。

用法：
    alembic upgrade head
    uvicorn app.main:app --port 18746 &
    python scripts/create_token.py --role owner --name e2e-owner   # 记下明文
    python scripts/create_token.py --role zhan_mcp --name e2e-zhan # 记下明文
    RV_OWNER_TOKEN=... RV_ZHAN_TOKEN=... python scripts/e2e_t3_check.py

任何一步不符合预期都会以非零退出码失败——不是 mock，不许假装成功。
"""

import os
import sys

import httpx

BASE = os.environ.get("RV_BASE", "http://127.0.0.1:18746")
OWNER_TOKEN = os.environ.get("RV_OWNER_TOKEN")
ZHAN_TOKEN = os.environ.get("RV_ZHAN_TOKEN")


def check(name: str, cond: bool, extra: str = "") -> None:
    if not cond:
        print(f"FAIL: {name} {extra}")
        sys.exit(1)
    print(f"ok: {name}")


def main() -> None:
    if not OWNER_TOKEN or not ZHAN_TOKEN:
        sys.exit("需要环境变量 RV_OWNER_TOKEN 和 RV_ZHAN_TOKEN（由 create_token.py 生成）")

    owner_headers = {"Authorization": f"Bearer {OWNER_TOKEN}"}
    zhan_headers = {"Authorization": f"Bearer {ZHAN_TOKEN}"}

    with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as c:
        check("health", c.get("/health").status_code == 200)
        check("anon 401", c.get("/api/conversations").status_code == 401)

        with open("tests/fixtures/chatgpt_export_sample.json", "rb") as f:
            r = c.post("/api/imports", files={"file": ("conversations.json", f)}, headers=zhan_headers)
        check("zhan import 403", r.status_code == 403)

        with open("tests/fixtures/chatgpt_export_sample.json", "rb") as f:
            r = c.post("/api/imports", files={"file": ("conversations.json", f)}, headers=owner_headers)
        check("owner import", r.status_code == 200 and r.json()["import_"]["status"] == "completed", r.text)

        conv = c.get("/api/conversations", headers=owner_headers).json()[0]
        msgs = c.get(f"/api/conversations/{conv['id']}/messages", headers=zhan_headers).json()
        check("zhan read messages", len(msgs) == 4)

        r = c.post(
            "/api/memories",
            json={
                "body": "Owner偏好安静、有空间感的环境。",
                "memory_type": "preference",
                "title": "居住偏好",
                "event_time_start": "2025-03-14",
                "actor_model": "gpt-5.6-sol",
            },
            headers=zhan_headers,
        )
        check("zhan create memory", r.status_code == 200, r.text)
        memory = r.json()
        check(
            "actor derived from token",
            memory["created_by_actor"] == "zhan_mcp" and memory["created_by_model"] == "gpt-5.6-sol",
        )

        r = c.post(
            f"/api/memories/{memory['id']}/spans",
            json={
                "conversation_id": conv["id"],
                "start_message_id": msgs[0]["id"],
                "end_message_id": msgs[1]["id"],
                "span_type": "evidence",
            },
            headers=zhan_headers,
        )
        check("zhan add evidence span", r.status_code == 200, r.text)

        r = c.patch(
            f"/api/memories/{memory['id']}",
            json={"body": "Owner偏好安静、柔和、有空间感的家。"},
            headers=owner_headers,
        )
        check("owner edit -> v3", r.status_code == 200 and r.json()["current_version"] == 3)

        detail = c.get(f"/api/memories/{memory['id']}", headers=zhan_headers).json()
        check(
            "genesis detail",
            len(detail["versions"]) == 3
            and len(detail["spans"]) == 1
            and [e["event_type"] for e in detail["audit_events"]]
            == ["memory_created", "span_added", "memory_updated"],
        )
        check(
            "event date separated",
            detail["memory"]["event_time_start"] == "2025-03-14"
            and detail["memory"]["created_at"][:4] >= "2026",
        )

        r = c.request("DELETE", f"/api/memories/{memory['id']}", json={}, headers=zhan_headers)
        check("zhan delete 403", r.status_code == 403)

        r = c.post(
            f"/api/memories/{memory['id']}/restore",
            json={"version_number": 1, "reason": "回滚验证"},
            headers=owner_headers,
        )
        check(
            "owner restore appends v4",
            r.status_code == 200
            and r.json()["current_version"] == 4
            and r.json()["body"] == "Owner偏好安静、有空间感的环境。",
        )

        detail = c.get(f"/api/memories/{memory['id']}", headers=owner_headers).json()
        check(
            "history intact after restore",
            len(detail["versions"]) == 4
            and detail["versions"][0]["snapshot"]["body"] == "Owner偏好安静、有空间感的环境。"
            and detail["versions"][2]["snapshot"]["body"] == "Owner偏好安静、柔和、有空间感的家。"
            and detail["versions"][3]["snapshot"]["body"] == "Owner偏好安静、有空间感的环境。",
        )

        r = c.request("DELETE", f"/api/memories/{memory['id']}", json={}, headers=owner_headers)
        check("owner soft delete", r.status_code == 200 and r.json()["status"] == "deleted")
        remaining = c.get("/api/memories", headers=owner_headers).json()
        check("deleted hidden by default", all(m["id"] != memory["id"] for m in remaining))

    print("E2E_T4_ALL_OK")


if __name__ == "__main__":
    main()
