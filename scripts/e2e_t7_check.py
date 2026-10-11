"""T7 端到端：真实 HTTP 导出 → 下载 → 用 CLI 脚本恢复到全新库 → 对账。

用法（backend/ 目录）：
    DB=e2e-t7-$(date +%H%M%S).db
    DATABASE_URL=sqlite:///./$DB alembic upgrade head
    python ../scripts/create_token.py --role owner --name e2e-t7-owner   # 记下明文
    DATABASE_URL=sqlite:///./$DB EXPORT_DIR=./exports-e2e-t7 \
        python -m uvicorn app.main:app --port 18770 &
    RV_BASE=http://127.0.0.1:18770 RV_OWNER_TOKEN=... python ../scripts/e2e_t7_check.py

恢复用的是 scripts/restore_from_export.py（子进程，真实 CLI），不是进程内调用。
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("RV_BASE", "http://127.0.0.1:18770")
OWNER_TOKEN = os.environ.get("RV_OWNER_TOKEN")
FIXTURE = REPO_ROOT / "backend" / "tests" / "fixtures" / "chatgpt_export_sample.json"
PY = sys.executable


def check(name: str, cond: bool, extra: str = "") -> None:
    if not cond:
        print(f"FAIL: {name} {extra}")
        sys.exit(1)
    print(f"ok: {name}")


def main() -> None:
    if not OWNER_TOKEN:
        sys.exit("需要环境变量 RV_OWNER_TOKEN")

    owner = {"Authorization": f"Bearer {OWNER_TOKEN}"}
    tmp = Path(tempfile.mkdtemp(prefix="rianvault-e2e-t7-"))
    try:
        with httpx.Client(base_url=BASE, timeout=120, trust_env=False) as c:
            check("health", c.get("/health").status_code == 200)

            with FIXTURE.open("rb") as f:
                r = c.post("/api/imports", files={"file": ("c.json", f)}, headers=owner)
            check("import", r.status_code == 200, r.text)

            conv = c.get("/api/conversations", headers=owner).json()[0]
            msgs = c.get(f"/api/conversations/{conv['id']}/messages", headers=owner).json()
            memory = c.post(
                "/api/memories",
                json={
                    "title": "导出往返验证",
                    "body": "这条记忆必须能从导出包里完整恢复回来。",
                    "memory_type": "note",
                    "event_time_start": "2023-11-14",
                    "actor_model": "gpt-5.6-sol",
                },
                headers=owner,
            ).json()
            check("create memory", "id" in memory, str(memory)[:200])
            span = c.post(
                f"/api/memories/{memory['id']}/spans",
                json={
                    "conversation_id": conv["id"],
                    "start_message_id": msgs[0]["id"],
                    "end_message_id": msgs[-1]["id"],
                    "span_type": "evidence",
                },
                headers=owner,
            )
            check("add span", span.status_code == 200, span.text)

            r = c.post("/api/export", headers=owner)
            check("export", r.status_code == 200, r.text)
            export_id = r.json()["export_id"]

            r = c.get(f"/api/export/{export_id}/download", headers=owner)
            check("download", r.status_code == 200 and r.content[:2] == b"PK")
            zip_path = tmp / export_id
            zip_path.write_bytes(r.content)

        # --- 用真实 CLI 恢复到全新库 ---
        restored_db = tmp / "restored.db"
        proc = subprocess.run(
            [
                PY,
                str(REPO_ROOT / "scripts" / "restore_from_export.py"),
                str(zip_path),
                "--database-url",
                f"sqlite:///{restored_db.as_posix()}",
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT / "backend"),
        )
        check(
            "restore CLI exits 0",
            proc.returncode == 0,
            (proc.stdout or "")[-500:] + (proc.stderr or "")[-500:],
        )

        with zipfile.ZipFile(zip_path) as zf:
            manifest = json.loads(zf.read("manifest.json"))

        con = sqlite3.connect(restored_db)
        counts = {
            table: con.execute(f"select count(*) from {table}").fetchone()[0]
            for table in ("conversations", "messages", "memories", "memory_versions", "memory_source_spans")
        }
        con.close()
        for table, value in counts.items():
            check(f"restored {table} == manifest", value == manifest["counts"][table], f"{value} vs {manifest['counts'][table]}")

        con = sqlite3.connect(restored_db)
        body = con.execute("select body from memories limit 1").fetchone()[0]
        event_time = con.execute("select event_time_start from memories limit 1").fetchone()[0]
        version = con.execute("select current_version from memories limit 1").fetchone()[0]
        con.close()
        check("restored body matches", body == "这条记忆必须能从导出包里完整恢复回来。", body)
        check("restored event_time is the original date, not today", event_time.startswith("2023-11-14"), event_time)
        check("restored version history preserved", version == 2, str(version))

        # --- 重复恢复不产生重复行 ---
        proc2 = subprocess.run(
            [
                PY,
                str(REPO_ROOT / "scripts" / "restore_from_export.py"),
                str(zip_path),
                "--database-url",
                f"sqlite:///{restored_db.as_posix()}",
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT / "backend"),
        )
        check("second restore exits 0", proc2.returncode == 0, proc2.stderr[-300:])
        con = sqlite3.connect(restored_db)
        again = con.execute("select count(*) from messages").fetchone()[0]
        con.close()
        check("second restore adds nothing", again == counts["messages"], str(again))

    finally:
        # 只清理自己刚建的临时目录（zip 与恢复库都在里面，不动其它任何文件）
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)

    print("E2E_T7_ALL_OK")


if __name__ == "__main__":
    main()
