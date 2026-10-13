"""冒烟：真实服务上走一遍「建记忆 → 绑来源 → 改来源范围」。"""

import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "backend" / "tests" / "fixtures" / "chatgpt_export_sample.json"
import os  # noqa: E402

TOKEN = os.environ.get("RV_OWNER_TOKEN")


def check(name, ok, extra=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"  {extra}" if extra and not ok else ""))
    if not ok:
        sys.exit(1)


def main():
    if not TOKEN:
        sys.exit("需要 RV_OWNER_TOKEN")
    h = {"Authorization": f"Bearer {TOKEN}"}
    for _ in range(40):
        try:
            if httpx.get(f"{BASE}/health", timeout=2, trust_env=False).status_code == 200:
                break
        except Exception:
            time.sleep(0.5)

    with httpx.Client(base_url=BASE, timeout=60, trust_env=False) as c:
        with FIXTURE.open("rb") as f:
            c.post("/api/imports", files={"file": ("s.json", f)}, headers=h)
        conv = c.get("/api/conversations", headers=h).json()[0]
        msgs = c.get(f"/api/conversations/{conv['id']}/messages", headers=h).json()
        check("读到会话消息", len(msgs) >= 3, str(len(msgs)))

        mem = c.post(
            "/api/memories",
            json={"title": "冒烟：改范围", "body": "原文范围需要修正。", "memory_type": "note"},
            headers=h,
        ).json()
        span = c.post(
            f"/api/memories/{mem['id']}/spans",
            json={
                "conversation_id": conv["id"],
                "start_message_id": msgs[0]["id"],
                "end_message_id": msgs[1]["id"],
                "span_type": "evidence",
            },
            headers=h,
        ).json()
        check("建来源片段", span.get("end_message_id") == msgs[1]["id"], str(span)[:200])

        v_before = c.get(f"/api/memories/{mem['id']}", headers=h).json()["memory"]["current_version"]
        r = c.request(
            "PATCH",
            f"/api/memories/{mem['id']}/spans/{span['id']}",
            json={"end_message_id": msgs[2]["id"], "reason": "冒烟改范围"},
            headers=h,
        )
        check("改范围 200", r.status_code == 200, r.text[:200])
        check("范围已更新", r.json()["end_message_id"] == msgs[2]["id"], r.text[:200])

        detail = c.get(f"/api/memories/{mem['id']}", headers=h).json()
        check(
            "版本已 bump",
            detail["memory"]["current_version"] == v_before + 1,
            f"{detail['memory']['current_version']} vs {v_before + 1}",
        )
        events = [e for e in detail["audit_events"] if e["event_type"] == "span_updated"]
        check("审计记 before/after", len(events) == 1 and "before" in events[0]["detail"], str(events)[:200])

    print("SMOKE_SPAN_UPDATE_OK")


if __name__ == "__main__":
    main()
