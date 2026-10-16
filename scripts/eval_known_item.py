"""known-item（自检索）评测：对比关键词 / 语义 / 混合三档检索，报告 Hit@K 与 MRR。

⚠️ 术语纪律：本评测是 **known-item / self-retrieval**，不是 Recall@K。
   它只支撑 **Hit@K**（top-K 里找没找到目标）和 **MRR**（目标平均排在第几位的倒数）。
   开放式 Precision@K / Recall@K 需要 pooled relevance judgment（人工判池），本脚本不做。

它的价值有两个：
  1. 受控对比：三档配置跑同一批查询、同一套标准答案，可比、可复现。
  2. 回归测试：如果「用原文原句搜原文」都搜不回来，那管线一定有 bug（切块错位 / 索引 stale / embedding 没生效）。

⚠️ 隐私：报告只含数字（qid / 排名 / 命中与否），不含任何聊天正文。

用法（在 backend/ 目录下，**必须先停掉后端**——Qdrant 本地模式单进程独占）：
    python ../scripts/eval_known_item.py                 # 用默认查询集
    python ../scripts/eval_known_item.py --k 10 --limit 5
    python ../scripts/eval_known_item.py --modes keyword,semantic
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import Message  # noqa: E402
from app.services import chunking, search_service  # noqa: E402
from app.services.embedding import get_embedding_provider  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("eval.run")

MODES = ("keyword", "semantic", "hybrid")


def rank_of(hits, target_id: str) -> int:
    """目标在结果里的名次（1-based）；没找到返回 0。"""
    for i, h in enumerate(hits, 1):
        if h.message_id == target_id:
            return i
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="known-item 检索评测（Hit@K / MRR）")
    ap.add_argument("--set", default=str(BACKEND / "exports" / "eval" / "known_item_set.json"))
    ap.add_argument("--modes", default=",".join(MODES))
    ap.add_argument("-k", "--k", type=int, default=10, help="Hit@K 的 K")
    ap.add_argument("--limit", type=int, default=20, help="每档检索取回多少条")
    ap.add_argument("--out", default=str(BACKEND / "exports" / "eval" / "known_item_report.json"))
    args = ap.parse_args()

    modes = [m.strip() for m in args.modes.split(",") if m.strip() in MODES]
    if not modes:
        print("没有合法模式，可选: " + ", ".join(MODES))
        return 1

    set_path = Path(args.set)
    if not set_path.exists():
        print(f"找不到查询集: {set_path}\n请先跑 eval_build_known_item_set.py")
        return 1
    payload = json.loads(set_path.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    if not items:
        print("查询集为空")
        return 1

    settings = get_settings()
    db = SessionLocal()
    provider = get_embedding_provider()  # bge-m3 只加载一次
    print(f"embedding: {provider.model_name}  dim={provider.dimension}")
    print(f"查询集: {set_path.name}  ({len(items)} 条)   模式: {', '.join(modes)}   K={args.k}")

    per_mode: dict[str, list[dict]] = {m: [] for m in modes}
    missing = 0
    try:
        for it in items:
            mid, ci = it["message_id"], it["chunk_index"]
            msg = db.get(Message, uuid.UUID(mid))
            if msg is None or not (msg.content_text or "").strip():
                missing += 1
                continue
            chunks = chunking.chunk_message(
                "", "", msg.content_text, max_tokens=settings.chunk_max_tokens
            )
            if ci >= len(chunks):
                ci = 0
            q = chunks[ci].text  # 用整块作为查询（与索引时的块一致）
            for m in modes:
                try:
                    hits = search_service.search(
                        db, q, mode=m, limit=args.limit, provider=provider
                    )
                except Exception as e:
                    logger.warning("search failed mode=%s: %s", m, e)
                    per_mode[m].append({"qid": it["qid"], "rank": 0, "error": str(e)[:80]})
                    continue
                r = rank_of(hits, mid)
                per_mode[m].append({"qid": it["qid"], "rank": r, "n_results": len(hits)})
    finally:
        db.close()

    n = len(items) - missing
    if n <= 0:
        print("没有可评测的查询")
        return 1

    print(f"\n有效查询: {n} 条" + (f"（{missing} 条取不到正文，已跳过）" if missing else ""))
    print("\n" + "=" * 58)
    print(f"{'mode':10s} {'Hit@1':>8s} {f'Hit@{args.k}':>8s} {'MRR':>8s} {'命中数':>8s}")
    print("-" * 58)
    summary = {}
    for m in modes:
        rs = [x.get("rank", 0) for x in per_mode[m]]
        hit1 = sum(1 for r in rs if 0 < r <= 1)
        hitk = sum(1 for r in rs if 0 < r <= args.k)
        mrr = sum((1.0 / r) if r > 0 else 0.0 for r in rs) / len(rs) if rs else 0.0
        summary[m] = {
            "n": len(rs),
            f"hit@1": round(hit1 / len(rs), 4) if rs else 0.0,
            f"hit@{args.k}": round(hitk / len(rs), 4) if rs else 0.0,
            "mrr": round(mrr, 4),
            "found": hitk,
        }
        print(f"{m:10s} {summary[m]['hit@1']:8.3f} {summary[m][f'hit@{args.k}']:8.3f} "
              f"{summary[m]['mrr']:8.3f} {hitk:8d}")
    print("=" * 58)
    print("\n读法：Hit@K = top-K 里找回目标的比例；MRR = 目标排名的倒数均值（1.0 = 总在第一）。")
    print("⚠️ 这不是 Recall@K。开放式 precision/recall 需要人工 pooled judgment，本评测不提供。")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "method": "known-item / self-retrieval",
                "metrics": ["Hit@1", f"Hit@{args.k}", "MRR"],
                "not_reported": ["Precision@K", "Recall@K", "nDCG — 需 pooled relevance judgment"],
                "privacy": "报告只含统计数字，不含任何聊天正文。",
                "query_set": set_path.name,
                "n_queries": n,
                "k": args.k,
                "limit": args.limit,
                "embedding_model": provider.model_name,
                "summary": summary,
                "per_mode_detail": per_mode,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n报告已写入: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
