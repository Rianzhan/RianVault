"""冒烟：并发语义检索不再 503（单例修复）+ 热态检索耗时 + 导入后自动建索引。"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

BASE = os.environ.get("RV_BASE", "http://127.0.0.1:8000")
REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "backend" / "tests" / "fixtures" / "chatgpt_export_sample.json"
TOKEN = os.environ.get("RV_OWNER_TOKEN")


def check(name: str, ok: bool, extra: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"  {extra}" if extra and not ok else ""))
    if not ok:
        sys.exit(1)


def main() -> None:
    if not TOKEN:
        sys.exit("需要 RV_OWNER_TOKEN")
    h = {"Authorization": f"Bearer {TOKEN}"}

    with httpx.Client(base_url=BASE, timeout=300, trust_env=False) as c:
        # 1) 并发语义检索：修复前第二个必然 503
        def one(i: int) -> tuple[int, str]:
            r = c.post("/api/search", json={"query": f"安静的房子 {i}", "mode": "semantic"}, headers=h)
            return r.status_code, r.text[:120]

        with ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(one, range(4)))
        codes = [r[0] for r in results]
        check("4 个并发语义检索全部成功（无 503）", all(x == 200 for x in codes), str(results))

        # 2) 热态耗时（模型已预热）
        times = []
        for i in range(3):
            t = time.time()
            r = c.post("/api/search", json={"query": f"找一段关于住处的对话 {i}", "mode": "hybrid"}, headers=h)
            times.append(time.time() - t)
            check(f"混合检索 #{i + 1} 成功", r.status_code == 200, r.text[:120])
        print(f"      热态检索耗时：{[f'{x:.2f}s' for x in times]}")

        # 3) 导入后自动建索引（后台线程）
        before = c.get("/api/stats", headers=h).json()["indexed_messages"]
        with FIXTURE.open("rb") as f:
            r = c.post("/api/imports", files={"file": ("s.json", f)}, headers=h)
        check("导入成功", r.status_code == 200, r.text[:200])
        # 后台线程慢慢跑，给一点时间让它至少开始
        deadline = time.time() + 120
        grew = False
        while time.time() < deadline:
            now = c.get("/api/stats", headers=h).json()["indexed_messages"]
            if now > before:
                grew = True
                break
            time.sleep(3)
        check("导入后索引自动增长（无需手动点）", grew, f"before={before}")

    print("SMOKE_INDEX_OK")


if __name__ == "__main__":
    main()
