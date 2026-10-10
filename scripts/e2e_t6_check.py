"""T6 端到端验证：真实 embedding（本地 bge-m3）+ 真实 Qdrant（本地模式）+ 真实 HTTP。

用法（backend/ 目录下，用一个全新的库）：
    rm -f e2e-t6.db && rm -rf data/qdrant-e2e-t6
    DATABASE_URL=sqlite:///./e2e-t6.db alembic upgrade head
    DATABASE_URL=sqlite:///./e2e-t6.db QDRANT_PATH=./data/qdrant-e2e-t6 \
        HF_HOME=./.hf-cache python -m uvicorn app.main:app --port 18760 &
    python ../scripts/create_token.py --role owner --name e2e-t6-owner
    python ../scripts/create_token.py --role zhan_mcp --name e2e-t6-zhan
    RV_BASE=http://127.0.0.1:18760 RV_OWNER_TOKEN=... RV_ZHAN_TOKEN=... \
        HF_HOME=./.hf-cache python ../scripts/e2e_t6_check.py

脚本会直接连同一份 Qdrant 本地目录做 payload 抽查，确认**正文没有进向量库**。
任何一步不符合预期都以非零退出码退出——不许用"看起来跑通了"冒充通过。
"""

import os
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]

BASE = os.environ.get("RV_BASE", "http://127.0.0.1:18760")
OWNER_TOKEN = os.environ.get("RV_OWNER_TOKEN")
ZHAN_TOKEN = os.environ.get("RV_ZHAN_TOKEN")
QDRANT_PATH = os.environ.get("QDRANT_PATH", str(REPO_ROOT / "backend" / "data" / "qdrant-e2e-t6"))
COLLECTION = os.environ.get("QDRANT_COLLECTION", "rianvault_chunks")

FIXTURE = REPO_ROOT / "backend" / "tests" / "fixtures" / "search_semantic_chat.json"

FORBIDDEN_KEYS = {"text", "content", "content_text", "body", "snippet", "content_raw", "title"}


def check(name: str, cond: bool, extra: str = "") -> None:
    if not cond:
        print(f"FAIL: {name} {extra}")
        sys.exit(1)
    print(f"ok: {name}")


def inspect_qdrant_payloads() -> tuple[int, set[str]]:
    """抽查 Qdrant 里真实落盘的 payload 键集合——正文泄漏检查必须看真实存储。"""
    from qdrant_client import QdrantClient

    client = QdrantClient(path=QDRANT_PATH)
    points, _ = client.scroll(collection_name=COLLECTION, limit=100, with_payload=True)
    keys: set[str] = set()
    for p in points:
        keys.update((p.payload or {}).keys())
    return len(points), keys


def main() -> None:
    if not OWNER_TOKEN or not ZHAN_TOKEN:
        sys.exit("需要环境变量 RV_OWNER_TOKEN 和 RV_ZHAN_TOKEN")

    owner = {"Authorization": f"Bearer {OWNER_TOKEN}"}
    zhan = {"Authorization": f"Bearer {ZHAN_TOKEN}"}

    with httpx.Client(base_url=BASE, timeout=600, trust_env=False) as c:
        check("health", c.get("/health").status_code == 200)

        with FIXTURE.open("rb") as f:
            r = c.post("/api/imports", files={"file": ("sem.json", f)}, headers=owner)
        check("import fixture", r.status_code == 200 and r.json()["import_"]["status"] == "completed", r.text)

        r = c.post("/api/index/build", json={"rebuild": True}, headers=zhan)
        check("zhan cannot rebuild index (403)", r.status_code == 403)

        r = c.post("/api/index/build", json={"rebuild": True}, headers=owner)
        stats = r.json()
        model_recorded = stats.get("model", "")
        check(
            "owner builds index with real local model",
            r.status_code == 200
            and stats["chunks"] >= 6
            and ("bge-m3" in model_recorded.lower()),
            r.text,
        )
        EXPECTED_MODEL = model_recorded

        r = c.post("/api/index/build", json={}, headers=owner)
        check("incremental build is idempotent", r.status_code == 200 and r.json()["upserted"] == 0, r.text)

        r = c.get("/api/index/status", headers=owner)
        body = r.json()
        check(
            "index status reports model",
            body["total_chunks"] >= 6 and EXPECTED_MODEL in body["models"],
            r.text,
        )

        # --- payload 红线：向量库里不许有正文 ---
        count, keys = inspect_qdrant_payloads()
        check("qdrant has points", count >= 6, str(count))
        check("no body text leaked into qdrant", not (keys & FORBIDDEN_KEYS), str(keys))

        # --- 语义检索：用不同措辞问同一件事 ---
        r = c.post(
            "/api/search",
            json={"query": "想找一个安静、采光好、带院子的住处", "mode": "semantic", "limit": 5},
            headers=owner,
        )
        hits = r.json()["hits"]
        check("semantic search returns hits", r.status_code == 200 and hits, r.text)
        check(
            "semantic top hit is the housing message",
            "搬家" in hits[0]["content_text"] or "安静" in hits[0]["content_text"],
            str(hits[0]),
        )

        # --- 关键词检索：精确命中 ---
        r = c.post(
            "/api/search", json={"query": "TaskGroup", "mode": "keyword"}, headers=zhan
        )
        hits = r.json()["hits"]
        check("zhan keyword search hits asyncio message", any("TaskGroup" in h["content_text"] for h in hits), r.text)

        # --- 过滤生效（过滤条件回查 PG，不依赖 payload） ---
        r = c.post(
            "/api/search",
            json={
                "query": "火锅",
                "mode": "hybrid",
                "filters": {"source_platform": "不存在的平台"},
            },
            headers=owner,
        )
        check("filter excludes everything", r.status_code == 200 and r.json()["count"] == 0, r.text)

        # --- 权限 ---
        r = c.post("/api/search", json={"query": "搬家"}, headers=None)
        check("anonymous search 401", r.status_code in (401, 403), str(r.status_code))

    print("E2E_T6_ALL_OK")


if __name__ == "__main__":
    main()
