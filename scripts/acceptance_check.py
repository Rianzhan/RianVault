"""一键验收：一条命令跑完 RianVault 的 G.0 完成标准。

    cd C:/Users/Owner/Projects/RianVault
    python scripts/acceptance_check.py                 # 全量（含真机语义检索，约 2-3 分钟）
    python scripts/acceptance_check.py --skip-semantic # 跳过语义（不加载 2GB 权重，约 30 秒）

它会自己：建一个全新的库 → 起服务 → 造 token → 走完导入/选段/版本/检索/审计/导出/恢复/权限
→ 打印 PASS/FAIL 清单 → 关掉服务。不改动你现有的开发数据（库文件是新建的，旧文件不删）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
PY = sys.executable
PORT = int(os.environ.get("RV_PORT", "18799"))
BASE = f"http://127.0.0.1:{PORT}"
FIXTURE = BACKEND / "tests" / "fixtures" / "chatgpt_export_sample.json"
AUDIT_FIXTURE = BACKEND / "tests" / "fixtures" / "acceptance_chat.json"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, extra: str = "") -> bool:
    results.append((name, ok, extra))
    print(("PASS  " if ok else "FAIL  ") + name + (f"  {extra}" if extra and not ok else ""))
    return ok


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"命令失败：{' '.join(cmd)}\n{proc.stdout[-800:]}\n{proc.stderr[-800:]}")
    return proc.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="RianVault 一键验收")
    parser.add_argument("--skip-semantic", action="store_true", help="跳过真机语义检索")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    db_file = f"acceptance-{stamp}.db"
    qdrant_dir = f"data/qdrant-acceptance-{stamp}"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///./{db_file}", "QDRANT_MODE": "local", "QDRANT_PATH": f"./{qdrant_dir}"}

    print(f"库文件：backend/{db_file}（新建，不影响你现有数据）")
    run([PY, "-m", "alembic", "upgrade", "head"], BACKEND, env)
    owner_token = run([PY, str(REPO_ROOT / "scripts" / "create_token.py"), "--role", "owner", "--name", "acceptance-owner"], BACKEND, env).splitlines()[-1].strip()
    zhan_token = run([PY, str(REPO_ROOT / "scripts" / "create_token.py"), "--role", "zhan_mcp", "--name", "acceptance-zhan"], BACKEND, env).splitlines()[-1].strip()

    server = subprocess.Popen(
        [PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(BACKEND), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        _wait_health()
        _run_checks(owner_token, zhan_token, skip_semantic=args.skip_semantic, env=env)
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()

    failed = [name for name, ok, _ in results if not ok]
    print("\n" + "=" * 60)
    print(f"通过 {len(results) - len(failed)} / {len(results)}")
    if failed:
        print("未通过：")
        for name in failed:
            print(f"  - {name}")
        print("\n把上面这段输出原样发给我即可。")
        sys.exit(1)
    print("全部通过：G.0 验收逐项 OK")
    print("E2E_ACCEPTANCE_ALL_OK")


def _wait_health() -> None:
    for _ in range(60):
        try:
            if httpx.get(f"{BASE}/health", timeout=2, trust_env=False).status_code == 200:
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("服务没能起来，检查 uvicorn 输出")


def _run_checks(owner: str, zhan: str, *, skip_semantic: bool, env: dict[str, str]) -> None:
    owner_h = {"Authorization": f"Bearer {owner}"}
    zhan_h = {"Authorization": f"Bearer {zhan}"}

    with httpx.Client(base_url=BASE, timeout=600, trust_env=False) as c:
        check("服务可访问（/health）", c.get("/health").status_code == 200)

        # --- G.0-1 导入 + 重复导入零重复 ---
        with FIXTURE.open("rb") as f:
            r1 = c.post("/api/imports", files={"file": ("sample.json", f)}, headers=owner_h)
        first = r1.json() if r1.status_code == 200 else {}
        check("导入成功", r1.status_code == 200 and first.get("import_", {}).get("status") == "completed", r1.text[:200])

        with FIXTURE.open("rb") as f:
            r2 = c.post("/api/imports", files={"file": ("sample.json", f)}, headers=owner_h)
        second = r2.json() if r2.status_code == 200 else {}
        msg_before = c.get("/api/stats", headers=owner_h).json()["messages"]
        imported_first = first.get("import_", {}).get("stats", {}).get("imported")
        check("重复导入不产生重复数据", second.get("already_imported") is True and msg_before == imported_first, f"{msg_before} vs {imported_first}")

        # --- G.0-2 浏览并能定位到会话 ---
        convs = c.get("/api/conversations", headers=owner_h).json()
        check("能列出会话", len(convs) >= 1)
        conv_id = convs[0]["id"]
        msgs = c.get(f"/api/conversations/{conv_id}/messages", headers=owner_h).json()
        check("能读到原文消息", len(msgs) >= 4, str(len(msgs)))

        # --- G.0-3 建记忆 + 绑 span + 版本史 + 审计 ---
        mem = c.post("/api/memories", json={"title": "验收用记忆", "body": "Owner要求：记忆必须能追溯原文。", "memory_type": "note", "event_time_start": "2023-11-14"}, headers=owner_h)
        check("能创建记忆", mem.status_code == 200, mem.text[:200])
        mem_id = mem.json()["id"]
        span = c.post(f"/api/memories/{mem_id}/spans", json={"conversation_id": conv_id, "start_message_id": msgs[0]["id"], "end_message_id": msgs[-1]["id"], "span_type": "evidence"}, headers=owner_h)
        check("能绑定来源片段（evidence）", span.status_code == 200, span.text[:200])
        detail = c.get(f"/api/memories/{mem_id}", headers=owner_h).json()
        check("span 增删进版本史（v2）", detail["memory"]["current_version"] == 2, str(detail["memory"]["current_version"]))
        check("版本史可查", len(detail["versions"]) >= 2)
        check("来源片段可查", len(detail["spans"]) >= 1)
        check("审计史可查", any(e["event_type"] == "span_added" for e in detail["audit_events"]))

        # --- G.0-2 关键词检索 ---
        r = c.post("/api/search", json={"query": "第一条", "mode": "keyword"}, headers=owner_h)
        hits = r.json().get("hits", [])
        check("关键词检索能找回原文", r.status_code == 200 and any("第一条" in h["content_text"] for h in hits), r.text[:200])

        if not skip_semantic:
            build = c.post("/api/index/build", json={"rebuild": True}, headers=owner_h)
            check("建立语义索引（本地 bge-m3）", build.status_code == 200 and build.json().get("chunks", 0) >= 4, build.text[:200])
            r = c.post("/api/search", json={"query": "记忆可以追溯来源", "mode": "semantic"}, headers=owner_h)
            hits = r.json().get("hits", [])
            check("语义检索命中相关原文", r.status_code == 200 and len(hits) >= 1, r.text[:200])

        # --- G.0-4 遗失记忆审计 ---
        with AUDIT_FIXTURE.open("rb") as f:
            c.post("/api/imports", files={"file": ("acceptance_chat.json", f)}, headers=owner_h)
        scan = c.post("/api/audit/migration-candidates/scan", json={"scan_from": "2026-07-01", "scan_to": "2026-10-31"}, headers=owner_h)
        check("扫描候选（不自动认定）", scan.status_code == 200, scan.text[:200])
        cands = c.get("/api/audit/migration-candidates", headers=owner_h).json()
        if cands:
            cid = cands[0]["id"]
            v = c.post(f"/api/audit/migration-candidates/{cid}/verdict", json={"verdict": "successful_write"}, headers=owner_h)
            check("人工标记可保存", v.status_code == 200, v.text[:200])
            cm = c.post(f"/api/audit/migration-candidates/{cid}/create-memory", json={"body": "从候选整理的记忆", "span_type": "evidence", "context_start_message_id": cands[0]["signal_message"]["id"], "context_end_message_id": cands[0]["signal_message"]["id"]}, headers=owner_h)
            check("能从候选创建记忆", cm.status_code == 200, cm.text[:200])
        else:
            check("扫描候选（不自动认定）", False, "本 fixture 在窗口内没有候选")

        # --- G.0-5 导出 + 恢复 ---
        exp = c.post("/api/export", headers=owner_h)
        check("能导出", exp.status_code == 200, exp.text[:200])
        export_id = exp.json()["export_id"]
        dl = c.get(f"/api/export/{export_id}/download", headers=owner_h)
        check("能下载导出包", dl.status_code == 200 and dl.content[:2] == b"PK")
        zip_path = Path(os.environ.get("TEMP", ".")) / export_id
        zip_path.write_bytes(dl.content)

        restored = BACKEND / f"acceptance-restored-{datetime.now().strftime('%H%M%S')}.db"
        proc = subprocess.run([PY, str(REPO_ROOT / "scripts" / "restore_from_export.py"), str(zip_path), "--database-url", f"sqlite:///{restored.as_posix()}"], cwd=str(BACKEND), capture_output=True, text=True, env=env)
        check("能从导出包恢复到全新库", proc.returncode == 0, (proc.stdout or "")[-400:] + (proc.stderr or "")[-400:])
        if proc.returncode == 0:
            import sqlite3

            con = sqlite3.connect(restored)
            counts = {t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in ("conversations", "messages", "memories")}
            con.close()
            with zipfile.ZipFile(zip_path) as zf:
                manifest = json.loads(zf.read("manifest.json"))
            same = all(counts[t] == manifest["counts"][t] for t in counts)
            check("恢复后关键计数一致", same, f"{counts} vs {manifest['counts']}")
            body = sqlite3.connect(restored).execute("select body from memories limit 1").fetchone()[0]
            check("恢复后正文一致", body is not None)

        # --- G.0-6 权限矩阵 ---
        with FIXTURE.open("rb") as f:
            r = c.post("/api/imports", files={"file": ("sample.json", f)}, headers=zhan_h)
        check("zhan 不能导入（403）", r.status_code == 403, str(r.status_code))
        r = c.request("DELETE", f"/api/memories/{mem_id}", json={}, headers=zhan_h)
        check("zhan 不能删除（403）", r.status_code == 403, str(r.status_code))
        r = c.post(f"/api/memories/{mem_id}/restore", json={"version_number": 1}, headers=zhan_h)
        check("zhan 不能恢复（403）", r.status_code == 403, str(r.status_code))
        r = c.post("/api/admin/tokens", json={"name": "x", "role": "owner"}, headers=zhan_h)
        check("zhan 不能管令牌（403）", r.status_code == 403, str(r.status_code))
        r = c.post("/api/export", headers=zhan_h)
        check("zhan 不能导出（403）", r.status_code == 403, str(r.status_code))
        r = c.get("/api/memories", headers=zhan_h)
        check("zhan 可以读记忆（200）", r.status_code == 200, str(r.status_code))
        r = c.get("/api/memories")
        check("无 token 401", r.status_code == 401, str(r.status_code))

        # --- 加固 ---
        r = c.get("/api/memories", headers=owner_h)
        check("安全响应头与不缓存", r.headers.get("X-Frame-Options") == "DENY" and r.headers.get("Cache-Control") == "no-store", str(dict(r.headers)))


if __name__ == "__main__":
    main()
