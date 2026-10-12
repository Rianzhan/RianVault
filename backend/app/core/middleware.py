"""HTTP 加固中间件：安全响应头 + 私内容不缓存 + 写操作限流。

本机/自有 VPS 上的私人档案馆，默认假设：
- 任何 /api 响应都不许被中间层缓存（Cache-Control: no-store）。
- 不允许被 iframe 嵌套、不允许 MIME 嗅探、不泄露 referrer。
- 写操作和检索要限流：本机自用也挡得住脚本失控与意外循环。
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import get_settings
from app.core.logging_setup import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# 限流只对"会改动数据 / 会消耗算力"的请求生效：GET 浏览不限制
LIMITED_METHODS = {"POST", "PATCH", "DELETE"}
LIMITED_PATH_PREFIXES = ("/api/",)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, enabled: bool = True) -> None:
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if self.enabled:
            for key, value in SECURITY_HEADERS.items():
                response.headers.setdefault(key, value)
            if request.url.path.startswith("/api"):
                # 私人内容：任何一层都不许缓存
                response.headers.setdefault("Cache-Control", "no-store")
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """简单的进程内滑动窗口限流（单实例足够；多实例再换 Redis）。"""

    def __init__(self, app: ASGIApp, per_minute: int = 120) -> None:
        super().__init__(app)
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _key(self, request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def _limited(self, request: Request) -> bool:
        if self.per_minute <= 0:
            return False
        if request.method not in LIMITED_METHODS:
            return False
        return any(request.url.path.startswith(p) for p in LIMITED_PATH_PREFIXES)

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._limited(request):
            return await call_next(request)

        key = self._key(request)
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.per_minute:
            logger.warning("rate limit hit ip=%s path=%s", key, request.url.path)
            return JSONResponse(
                status_code=429,
                content={"detail": f"请求过于频繁（每分钟 {self.per_minute} 次上限）"},
            )
        window.append(now)
        return await call_next(request)


def install_middleware(app) -> None:
    settings = get_settings()
    app.add_middleware(SecurityHeadersMiddleware, enabled=settings.security_headers)
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
