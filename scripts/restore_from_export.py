"""从 RianVault 导出包恢复数据库。

用法：
    python scripts/restore_from_export.py exports/rianvault-export-20261011-100000.zip \
        --database-url sqlite:///./restored.db
    DATABASE_URL=... python scripts/restore_from_export.py <zip>   # 也可用环境变量

行为：
- 先校验 manifest + checksums.sha256，任何一项不符就中止（不静默继续）。
- 按主键原样写回，重复恢复不会重复插入。
- 恢复完打印对账计数；与 manifest 不一致会以非零退出码失败。
- 向量不恢复：跑 `python ../backend/../scripts/rebuild_qdrant.py` 重算即可。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.restore_service import RestoreError, count_all, restore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="从 Portable Export zip 重建 RianVault 数据库")
    parser.add_argument("zip_path", help="导出包路径")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="目标数据库；不给则读 DATABASE_URL（务必确认不是生产库！）",
    )
    parser.add_argument(
        "--no-create-tables",
        action="store_true",
        help="不自动建表（生产环境请先用 alembic upgrade head）",
    )
    args = parser.parse_args()

    if not args.database_url:
        sys.exit("缺少 --database-url 或 DATABASE_URL 环境变量")

    try:
        report = restore(
            Path(args.zip_path),
            args.database_url,
            create_tables=not args.no_create_tables,
        )
    except RestoreError as e:
        sys.exit(f"恢复失败：{e}")

    print(f"restore from {args.zip_path}")
    for name in report.restored:
        print(
            f"  {name:24s} restored={report.restored[name]:6d} skipped={report.skipped[name]:6d}"
        )
    print("counts in target db:")
    for name, value in count_all(args.database_url).items():
        print(f"  {name:24s} {value}")
    print("done: 向量索引请用 rebuild_qdrant.py 重建")


if __name__ == "__main__":
    main()
