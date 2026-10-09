"""T3 端到端验证脚本：走真实 HTTP API，验证 memory 生命周期。

用法：先启动 API（uvicorn app.main:app --port 18746），再运行本脚本。
任何一步不符合预期都会以非零退出码失败——不是 mock，不许假装成功。
"""

import sys

import httpx

BASE = "http://127.0.0.1:18746"


def check(name: str, cond: bool, extra: str = "") -> None:
    if not cond:
        print(f"FAIL: {name} {extra}")
        sys.exit(1)
    print(f"ok: {name}")


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.get("/health")
        check("health", r.status_code == 200)

        with open("tests/fixtures/chatgpt_export_sample.json", "rb") as f:
            r = c.post("/api/imports", files={"file": ("conversations.json", f)})
        check("import", r.status_code == 200 and r.json()["import_"]["status"] == "completed")

        conv = c.get("/api/conversations").json()[0]
        msgs = c.get(f"/api/conversations/{conv['id']}/messages").json()
        check("messages imported", len(msgs) == 4)

        r = c.post(
            "/api/memories",
            json={
                "body": "Owner偏好安静、有空间感的环境。",
                "memory_type": "preference",
                "title": "居住偏好",
                "event_time_start": "2025-03-14",
                "actor": "zhan_mcp",
                "actor_model": "gpt-5.6-sol",
            },
        )
        check("create memory", r.status_code == 200, r.text)
        memory = r.json()
        check("v1 + actor recorded", memory["current_version"] == 1
              and memory["created_by_actor"] == "zhan_mcp")

        r = c.post(
            f"/api/memories/{memory['id']}/spans",
            json={
                "conversation_id": conv["id"],
                "start_message_id": msgs[0]["id"],
                "end_message_id": msgs[1]["id"],
                "span_type": "evidence",
                "actor": "zhan_mcp",
            },
        )
        check("add evidence span", r.status_code == 200, r.text)

        r = c.patch(
            f"/api/memories/{memory['id']}",
            json={"body": "Owner偏好安静、柔和、有空间感的家。", "actor": "owner"},
        )
        check("edit memory -> v3", r.status_code == 200
              and r.json()["current_version"] == 3)

        detail = c.get(f"/api/memories/{memory['id']}").json()
        check("genesis detail", len(detail["versions"]) == 3
              and len(detail["spans"]) == 1
              and [e["event_type"] for e in detail["audit_events"]]
              == ["memory_created", "span_added", "memory_updated"])
        check("event date separated", detail["memory"]["event_time_start"] == "2025-03-14"
              and detail["memory"]["created_at"][:4] >= "2026")

        r = c.post(
            f"/api/memories/{memory['id']}/restore",
            json={"version_number": 1, "actor": "owner", "reason": "回滚验证"},
        )
        check("restore appends v4", r.status_code == 200
              and r.json()["current_version"] == 4
              and r.json()["body"] == "Owner偏好安静、有空间感的环境。")

        detail = c.get(f"/api/memories/{memory['id']}").json()
        check(
            "history intact after restore",
            len(detail["versions"]) == 4
            and detail["versions"][0]["snapshot"]["body"] == "Owner偏好安静、有空间感的环境。"
            and detail["versions"][2]["snapshot"]["body"] == "Owner偏好安静、柔和、有空间感的家。"
            and detail["versions"][3]["snapshot"]["body"] == "Owner偏好安静、有空间感的环境。",
        )

        r = c.request("DELETE", f"/api/memories/{memory['id']}", json={"actor": "owner"})
        check("soft delete", r.status_code == 200 and r.json()["status"] == "deleted")
        remaining = c.get("/api/memories").json()
        check("deleted hidden by default", all(m["id"] != memory["id"] for m in remaining))

    print("E2E_T3_ALL_OK")


if __name__ == "__main__":
    main()
