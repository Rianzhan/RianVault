"""统一异常处理。

纪律：**不吞异常**。
- 未处理异常 → 记 ERROR（带 error_id）+ 返回 500，响应体绝不含"成功"字样，
  也不回吐异常细节（可能夹带正文）。
- 参数校验失败 → 422，只回字段位置信息。
- 业务异常（HTTPException）→ 保持原样。
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging_setup import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

INTERNAL_MESSAGE = "服务器内部错误（已记录 error_id，请查服务端日志）"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 回显校验错误时也要小心：不回显用户提交的原始值（可能夹带正文）
        errors = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", "invalid")} for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": "参数校验失败", "errors": errors})

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        error_id = uuid.uuid4().hex[:12]
        # 注意：SQLAlchemy 的异常文本可能夹带 SQL 参数（也就是正文），
        # 所以默认只记类型与 error_id；只有显式开 debug 才打完整堆栈。
        if get_settings().debug:
            logger.exception(
                "unhandled error id=%s path=%s ip=%s type=%s",
                error_id,
                request.url.path,
                _client_ip(request),
                type(exc).__name__,
            )
        else:
            logger.error(
                "unhandled error id=%s path=%s ip=%s type=%s",
                error_id,
                request.url.path,
                _client_ip(request),
                type(exc).__name__,
            )
        return JSONResponse(
            status_code=500,
            content={"detail": INTERNAL_MESSAGE, "error_id": error_id},
        )
