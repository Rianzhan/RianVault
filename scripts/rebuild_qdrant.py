"""一键重建 Qdrant 语义索引（Qdrant 是可丢弃索引，PG 才是权威真源）。

用法（在 backend/ 目录下）：
    python ../scripts/rebuild_qdrant.py            # 全量重建
    python ../scripts/rebuild_qdrant.py --limit 50 # 只索引前 50 条消息（冒烟用）
    python ../scripts/rebuild_qdrant.py --check    # 只报告状态，不动索引

注意：换 embedding 模型必须全量重建（向量空间变了）；脚本会打印当前模型。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import func, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import ChunkIndex, Message  # noqa: E402
from app.services import index_service  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("rebuild")


def report(db) -> None:
    settings = get_settings()
    total_messages = db.scalar(select(func.count(Message.id))) or 0
    indexed_models = {
        model: count
        for model, count in db.execute(
            select(ChunkIndex.embedding_model, func.count(ChunkIndex.id)).group_by(
                ChunkIndex.embedding_model
            )
        ).all()
    }
    indexed_messages = (
        db.scalar(select(func.count(func.distinct(ChunkIndex.message_id)))) or 0
    )
    print(f"collection      : {settings.qdrant_collection} (mode={settings.qdrant_mode})")
    print(f"embedding model : {settings.embedding_model}")
    print(f"messages        : {total_messages}")
    print(f"indexed messages: {indexed_messages}")
    print(f"chunks by model : {indexed_models or '{}'}")
    stale = {m: c for m, c in indexed_models.items() if m != settings.embedding_model}
    if stale:
        print(f"! 存在其他模型的向量（{stale}），需要 --rebuild 全量重建")


def main() -> None:
    parser = argparse.ArgumentParser(description="重建 RianVault 的 Qdrant 语义索引")
    parser.add_argument("--rebuild", action="store_true", help="清空集合后全量重建（默认增量）")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 条消息")
    parser.add_argument("--check", action="store_true", help="只打印状态，不写索引")
    args = parser.parse_args()

    with SessionLocal() as db:
        report(db)
        if args.check:
            return
        stats = index_service.index_messages(db, rebuild=args.rebuild, limit_messages=args.limit)
        print(
            f"done: messages={stats['messages']} chunks={stats['chunks']} "
            f"skipped_empty={stats['skipped_empty']} model={stats['model']}"
        )
        report(db)


if __name__ == "__main__":
    main()
