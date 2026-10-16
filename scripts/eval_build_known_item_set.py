"""构造 known-item（自检索）评测用的查询集，并逐条验证「标准答案唯一」。

这个方法在 IR 里叫 known-item retrieval：从库里抽一条消息，取它自己的一句话当查询，
看检索系统能不能在 top-K 里把它找回来。**正确答案是构造出来的，不是人工判出来的**——
所以不需要任何人工标注，但必须验证「这句话是不是只在这一条消息里出现」。

⚠️ 隐私设计（重要）：
  本脚本会读取聊天正文（ unavoidable，要构造查询就必须读），但
  **输出文件里只有 message_id / chunk_index / 长度 / 命中数，不含任何正文**。
  句子本身只在内存里用于检索验证，默认不打印、不落盘。
  输出目录默认 backend/exports/eval/，已被 .gitignore 的 `exports/` 覆盖。

用法（在 backend/ 目录下运行，且**必须先停掉后端**——Qdrant 本地模式单进程独占）：
    python ../scripts/eval_build_known_item_set.py --check          # 只看状态
    python ../scripts/eval_build_known_item_set.py --n 30            # 生成 30 条
    python ../scripts/eval_build_known_item_set.py --n 30 --show-examples 3
                                                                    # 额外打印 3 条句子供人工确认（打印到终端，不落盘）

产物：backend/exports/eval/known_item_set.json —— 交给 eval_known_item.py 跑正式评测。
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import ChunkIndex, Message  # noqa: E402
from app.services import chunking, search_service  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("eval.build")

# 应声词 / 无信息量句子：这类当 query 会在库里命中几百条，不能作为标准答案
FILLER = re.compile(
    r"^\W*(嗯+|哦+|啊+|好+的?|是+的?|对+|行+吧?|哈哈+|呵呵+|知道了?|明白[了的]?|"
    r"ok+|yes+|no+|thanks?|thank you+|sorry+|hmm+|hey+|hi+|bye+|"
    r"[\.\,\!\?\s\~\-…。！？，、]+)\W*$",
    re.IGNORECASE,
)
# 单独的 URL / 纯数字 / 极短
NOISE = re.compile(r"^\W*(\d+[\d\s\.\-]*|https?://\S+|[^\w\u4e00-\u9fff]+)\W*$", re.IGNORECASE)


def pick_sentence(text: str, min_chars: int) -> str | None:
    """从一段文本里挑一句「有信息量」的话当查询。取最长的那句（信息量最大、最不容易撞车）。"""
    if not text:
        return None
    parts = [p.strip() for p in chunking._SENTENCE_SPLIT.split(text) if p and p.strip()]
    if not parts:
        parts = [text.strip()]
    cands = []
    for p in parts:
        if len(p) < min_chars:
            continue
        if FILLER.match(p) or NOISE.match(p):
            continue
        cands.append(p)
    if not cands:
        return None
    return max(cands, key=len)


def main() -> int:
    ap = argparse.ArgumentParser(description="构造 known-item 查询集并验证答案唯一性")
    ap.add_argument("--n", type=int, default=30, help="最终要多少条可用查询")
    ap.add_argument("--pool", type=int, default=400, help="抽多少条消息作为候选池")
    ap.add_argument("--min-chars", type=int, default=24, help="候选句子最短字符数")
    ap.add_argument("--max-chars", type=int, default=180, help="候选句子最长字符数（太长会退化成整段）")
    ap.add_argument("--seed", type=int, default=42, help="随机种子，保证可复现")
    ap.add_argument("--show-examples", type=int, default=0, help="额外打印 N 条句子到终端（不落盘）")
    ap.add_argument("--limit-uniqueness", type=int, default=20, help="唯一性验证时看多少条检索结果")
    ap.add_argument("--out", default=str(BACKEND / "exports" / "eval" / "known_item_set.json"))
    ap.add_argument("--check", action="store_true", help="只报告状态，不生成")
    args = ap.parse_args()

    settings = get_settings()
    db = SessionLocal()
    try:
        # 已索引的（message_id, chunk_index）——只在已索引消息里出题，
        # 否则语义检索根本搜不到它，评测就不公平。
        rows = db.execute(
            select(ChunkIndex.message_id, ChunkIndex.chunk_index, ChunkIndex.token_estimate)
        ).all()
        indexed: dict[str, list[tuple[int, int]]] = {}
        for mid, ci, tok in rows:
            indexed.setdefault(str(mid), []).append((int(ci), int(tok or 0)))
        total_indexed_msgs = len(indexed)
        if args.check:
            total_msgs = db.execute(select(Message.id)).scalars().all()
            print(f"messages(total)   : {len(total_msgs):,}")
            print(f"messages(indexed) : {total_indexed_msgs:,}")
            print(f"chunks            : {len(rows):,}")
            print(f"embedding model   : {settings.embedding_model}")
            return 0
        if not indexed:
            print("没有任何已索引消息，请先跑 scripts/rebuild_qdrant.py")
            return 1

        rng = random.Random(args.seed)
        pool_ids = list(indexed.keys())
        rng.shuffle(pool_ids)
        pool_ids = pool_ids[: args.pool]

        accepted, rejected = [], []
        reject_reasons: dict[str, int] = {}

        for i, mid in enumerate(pool_ids, 1):
            if len(accepted) >= args.n:
                break
            msg = db.get(Message, uuid.UUID(mid))
            if msg is None or not (msg.content_text or "").strip():
                reject_reasons["no_text"] = reject_reasons.get("no_text", 0) + 1
                continue

            # 用与索引相同的切块规则重切，取目标 chunk 的文本
            try:
                chunks = chunking.chunk_message(
                    "", "", msg.content_text, max_tokens=settings.chunk_max_tokens
                )
            except Exception:
                reject_reasons["chunk_failed"] = reject_reasons.get("chunk_failed", 0) + 1
                continue
            if not chunks:
                reject_reasons["no_chunk"] = reject_reasons.get("no_chunk", 0) + 1
                continue

            # 优先用已索引的 chunk；取 token 最多的那个（内容最实）
            pairs = sorted(indexed[mid], key=lambda x: -x[1])
            ci = pairs[0][0]
            if ci >= len(chunks):
                ci = 0
            src_text = chunks[ci].text

            q = pick_sentence(src_text, args.min_chars)
            if not q:
                reject_reasons["no_informative_sentence"] = reject_reasons.get("no_informative_sentence", 0) + 1
                continue
            if len(q) > args.max_chars:
                reject_reasons["too_long"] = reject_reasons.get("too_long", 0) + 1
                continue

            # —— 唯一性验证：这句话在库里到底能搜出几条？——
            try:
                hits = search_service.keyword_search(db, q, limit=args.limit_uniqueness)
            except Exception as e:
                logger.warning("keyword search failed: %s", e)
                reject_reasons["search_error"] = reject_reasons.get("search_error", 0) + 1
                continue
            got = {h.message_id for h in hits}
            if mid not in got:
                reject_reasons["self_not_found"] = reject_reasons.get("self_not_found", 0) + 1
                continue
            if len(got) > 1:
                reject_reasons["not_unique"] = reject_reasons.get("not_unique", 0) + 1
                continue

            accepted.append(
                {
                    "qid": f"k{len(accepted) + 1:03d}",
                    "message_id": str(mid),
                    "chunk_index": ci,
                    "query_chars": len(q),
                    "query_tokens": int(chunking.estimate_tokens(q)),
                    "role": msg.role,
                    # 句子本身不落盘；需要时由 eval_known_item.py 按 (message_id, chunk_index) 现取
                }
            )
            if args.show_examples and len(accepted) <= args.show_examples:
                print(f"\n[示例 {len(accepted)}] message_id={str(mid)[:8]}… chunk={ci} "
                      f"({len(q)}字, 关键词命中 {len(got)} 条 → 答案唯一)")
                print(f"  query: {q}")
            if i % 50 == 0:
                logger.warning("已扫描 %d 条候选，采纳 %d 条", i, len(accepted))
    finally:
        db.close()

    print(f"\n候选池扫描         : {min(len(pool_ids), args.pool)} 条")
    print(f"采纳（答案唯一）   : {len(accepted)} 条")
    print(f"丢弃               : {sum(reject_reasons.values())} 条")
    for k, v in sorted(reject_reasons.items(), key=lambda x: -x[1]):
        print(f"   - {k:26s} {v}")

    if not accepted:
        print("\n没有可用查询，试试放宽 --min-chars 或加大 --pool")
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "method": "known-item / self-retrieval",
        "metrics_planned": ["Hit@K", "MRR"],
        "note": ("这是 known-item 自检索，不是 Recall@K；开放式 Precision/Recall "
                 "需要 pooled relevance judgment，本集不做。"),
        "privacy": ("本文件只含 message_id / chunk_index / 统计值，不含任何聊天正文；"
                    "查询句子由评测脚本按 ID 现取。"),
        "seed": args.seed,
        "min_chars": args.min_chars,
        "max_chars": args.max_chars,
        "indexed_messages_total": total_indexed_msgs,
        "embedding_model": settings.embedding_model,
        "items": accepted,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入: {out}")
    print(f"   （该目录已被 .gitignore 的 exports/ 覆盖，不会进 Git）")
    print(f"\n下一步：python ../scripts/eval_known_item.py --set {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
