"""铸造 API token：写入 api_tokens 表（SHA-256 哈希），明文只显示一次。

用法（在 backend/ 目录或仓库根均可，需 DATABASE_URL 指向目标库）：
    python scripts/create_token.py --role owner --name "Owner的主 token"
    python scripts/create_token.py --role zhan_mcp --name "湛（GPT-5.6 Sol）"
    python scripts/create_token.py --list
    python scripts/create_token.py --revoke <token_id>
"""

import argparse
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.security import ROLES, generate_token, hash_token  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import ApiToken  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="RianVault API token 管理")
    parser.add_argument("--role", choices=sorted(ROLES))
    parser.add_argument("--name")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--revoke")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.list:
            for t in db.scalars(select(ApiToken).order_by(ApiToken.created_at)):
                state = "revoked" if t.revoked_at else "active"
                print(f"{t.id}  {t.role:<10}  {state:<8}  {t.name}")
            return

        if args.revoke:
            row = db.get(ApiToken, uuid.UUID(args.revoke))
            if row is None:
                sys.exit("token 不存在")
            row.revoked_at = datetime.now(UTC)
            db.commit()
            print(f"已吊销: {row.id} ({row.name})")
            return

        if not args.role or not args.name:
            parser.error("铸造需要 --role 和 --name")

        plaintext = generate_token()
        row = ApiToken(
            id=uuid.uuid4(), name=args.name, role=args.role, token_hash=hash_token(plaintext)
        )
        db.add(row)
        db.commit()
        print(f"已创建 {args.role} token: {row.id} ({args.name})")
        print(f"明文（只显示这一次，请立即保存）:\n{plaintext}")


if __name__ == "__main__":
    main()
