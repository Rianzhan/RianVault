"""Token 生成与哈希。高熵随机 token 用 SHA-256 足够（非用户密码，
无需慢哈希；未来 Owner 登录密码会用 Argon2id，另行设计）。"""

import hashlib
import secrets

ROLES = {"owner", "zhan_mcp"}


def generate_token() -> str:
    """生成 256-bit 随机 token。明文只返回这一次，永不入库。"""
    return f"rv_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
