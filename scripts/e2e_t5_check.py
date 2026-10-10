"""T5 端到端验证：遗失记忆审计（真实 HTTP + 真实 token + 真实导入数据）。

用法：
    alembic upgrade head
    uvicorn app.main:app --port 18747 &
    python scripts/create_token.py --role owner --name e2e-owner   # 记下明文
    python scripts/create_token.py --role zhan_mcp --name e2e-zhan # 记下明文
    RV_BASE=http://127.0.0.1:18747 RV_OWNER_TOKEN=... RV_ZHAN_TOKEN=... \
        python scripts/e2e_t5_check.py

任何一步不符合预期都以非零退出码失败——不用 mock，不许假装成功。
审计只产出 candidate，是否真是"写入成功的长期记忆"必须由 Owner 判断。
"""

import os
import sys

import httpx

BASE = os.environ.get("RV_BASE", "http://127.0.0.1:18747")
OWNER_TOKEN = os.environ.get("RV_OWNER_TOKEN")
ZHAN_TOKEN = os.environ.get("RV_ZHAN_TOKEN")

FIXTURE = "backend/tests/fixtures/migration_signals_chat.json"
SCAN_FROM = "2026-06-01"
SCAN_TO = "2026-07-31"


def check(name: str, cond: bool, extra: str = "") -> None:
    if not cond:
        print(f"FAIL: {name} {extra}")
        sys.exit(1)
    print(f"ok: {name}")


def main() -> None:
    if not OWNER_TOKEN or not ZHAN_TOKEN:
        sys.exit("需要环境变量 RV_OWNER_TOKEN 和 RV_ZHAN_TOKEN（由 create_token.py 生成）")

    owner = {"Authorization": f"Bearer {OWNER_TOKEN}"}
    zhan = {"Authorization": f"Bearer {ZHAN_TOKEN}"}

    with httpx.Client(base_url=BASE, timeout=60, trust_env=False) as c:
        check("health", c.get("/health").status_code == 200)
        check("anon 401", c.get("/api/audit/migration-candidates", params={"limit": 1}).status_code == 401)

        with open(FIXTURE, "rb") as f:
            r = c.post("/api/imports", files={"file": ("migration_signals_chat.json", f)}, headers=owner)
        check("owner import fixture", r.status_code == 200 and r.json()["import_"]["status"] == "completed", r.text)

        # --- 扫描：仅 Owner ---
        r = c.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": SCAN_FROM, "scan_to": SCAN_TO},
            headers=zhan,
        )
        check("zhan scan 403", r.status_code == 403)

        r = c.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": SCAN_FROM, "scan_to": SCAN_TO},
            headers=owner,
        )
        first = r.json()
        check(
            "owner scan finds candidates",
            r.status_code == 200 and first["created"] >= 2 and first["total"] == first["created"],
            r.text,
        )

        # --- 幂等：重复扫描不产生重复候选 ---
        r = c.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": SCAN_FROM, "scan_to": SCAN_TO},
            headers=owner,
        )
        second = r.json()
        check(
            "scan idempotent",
            second["created"] == 0
            and second["existing"] == first["total"]
            and second["total"] == first["total"],
            r.text,
        )

        # --- 候选列表：默认 unreviewed，带上下文供人工审阅 ---
        r = c.get("/api/audit/migration-candidates", params={"limit": 100}, headers=zhan)
        candidates = r.json()
        check("zhan can list candidates", r.status_code == 200 and len(candidates) == first["total"], r.text)
        check(
            "candidates unreviewed by default",
            all(x["verdict"] == "unreviewed" for x in candidates),
        )
        check(
            "candidates carry context window",
            all(x["context"] and x["signal_message"]["content_text"] for x in candidates),
        )

        # --- 时间窗外不命中 ---
        r = c.post(
            "/api/audit/migration-candidates/scan",
            json={"scan_from": "2025-01-01", "scan_to": "2025-01-31"},
            headers=owner,
        )
        check("scan outside window finds nothing", r.status_code == 200 and r.json()["total"] == 0, r.text)

        # --- 判定：合法 verdict 落库，非法 verdict 拒绝 ---
        target = next(x for x in candidates if "更新记忆" in x["signal_message"]["content_text"])
        r = c.post(
            f"/api/audit/migration-candidates/{target['id']}/verdict",
            json={"verdict": "successful_write", "note": "上下文显示确实写入了"},
            headers=zhan,
        )
        check("zhan set verdict", r.status_code == 200 and r.json()["verdict"] == "successful_write", r.text)

        r = c.post(
            f"/api/audit/migration-candidates/{target['id']}/verdict",
            json={"verdict": " definitely_written "},
            headers=owner,
        )
        check("invalid verdict 400", r.status_code == 400, r.text)

        # --- 从候选建记忆：绑定 Owner 选定的 span 范围 ---
        ctx_start = target["context"][0]["id"]
        ctx_end = target["context"][-1]["id"]
        r = c.post(
            f"/api/audit/migration-candidates/{target['id']}/create-memory",
            json={
                "body": "2026-06 曾要求把「这件事」写入长期记忆，助手回复已记住。",
                "title": "2026-06 记忆写入线索",
                "memory_type": "note",
                "span_type": "evidence",
                "context_start_message_id": ctx_start,
                "context_end_message_id": ctx_end,
                "actor_model": "gpt-5.6-sol",
            },
            headers=zhan,
        )
        created = r.json()
        # v1 = 创建，v2 = 绑定证据 span（span 增删必须进版本历史，这是设计约定，不是噪音）
        check(
            "create memory from candidate",
            r.status_code == 200 and created["current_version"] == 2,
            r.text,
        )
        memory_id = created["memory_id"]

        detail = c.get(f"/api/memories/{memory_id}", headers=owner).json()
        mem = detail["memory"]
        check(
            "span addition is a versioned event",
            len(detail["versions"]) == 2
            and not detail["versions"][0]["snapshot"]["spans"]
            and len(detail["versions"][1]["snapshot"]["spans"]) == 1,
            str([len(v["snapshot"].get("spans", [])) for v in detail["versions"]]),
        )
        check(
            "memory traces back to signal span",
            len(detail["spans"]) == 1
            and detail["spans"][0]["span_type"] == "evidence"
            and detail["spans"][0]["start_message_id"] == ctx_start
            and detail["spans"][0]["end_message_id"] == ctx_end,
        )
        check(
            "provenance recorded",
            mem["created_by_actor"] == "zhan_mcp" and mem["created_by_model"] == "gpt-5.6-sol",
            str(mem),
        )
        check(
            "event_time defaults from signal message, not ingestion time",
            mem["event_time_start"] == target["signal_message"]["event_time"][:10],
            f"{mem['event_time_start']} vs {target['signal_message']['event_time']}",
        )
        check(
            "audit trail written",
            [e["event_type"] for e in detail["audit_events"]] == ["memory_created", "span_added"],
            str(detail["audit_events"]),
        )

        # --- 候选被关联，且不会因二次建记忆而重复 ---
        r = c.get("/api/audit/migration-candidates", params={"verdict": "successful_write"}, headers=owner)
        linked = [x for x in r.json() if x["id"] == target["id"]]
        check(
            "candidate linked to memory",
            len(linked) == 1 and linked[0]["linked_memory_id"] == memory_id,
            r.text,
        )

        r = c.post(
            f"/api/audit/migration-candidates/{target['id']}/create-memory",
            json={"body": "重复建一次应被拒绝"},
            headers=owner,
        )
        check("duplicate create rejected", r.status_code == 400, r.text)

    print("E2E_T5_ALL_OK")


if __name__ == "__main__":
    main()
