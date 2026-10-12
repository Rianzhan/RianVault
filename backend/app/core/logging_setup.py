"""日志：结构化、凭据脱敏、绝不记录正文。

红线：日志里不允许出现 token、Authorization、原文正文、查询词。
- 这里提供一道**兜底过滤器**：即使有人手滑写了 logger.info(f"...{token}")，也会被抹掉。
- 真正的保证还是"不写"，过滤器只作为最后一道网（defense in depth）。
"""

from __future__ import annotations

import logging
import re

LOGGER_NAME = "rianvault"

# (pattern, replacement)
_SENSITIVE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{4,}", re.IGNORECASE), r"\1***"),
    (re.compile(r"\brv_[A-Za-z0-9_\-]{4,}", re.IGNORECASE), "rv_***"),
    (
        re.compile(r"([?&](?:token|api_key|access_token|password)=)[^&\s\"']+", re.IGNORECASE),
        r"\1***",
    ),
    (re.compile(r"(://[^/\s:@]+:)[^@\s]+@"), r"\1***@"),  # 数据库连接串里的密码
]

# 正文类字段：一旦出现在日志的 key=value 形式里就整体抹掉
_BODY_KEYS = re.compile(
    r"\b(content_text|body|content|snippet|query|text)\s*=\s*(\"[^\"]*\"|'[^']*'|\S+)",
    re.IGNORECASE,
)


def redact(message: str) -> str:
    out = message
    for pattern, replacement in _SENSITIVE:
        out = pattern.sub(replacement, out)
    return _BODY_KEYS.sub(r"\1=***", out)


class SensitiveDataFilter(logging.Filter):
    """把 token / 凭据 / 正文字段从日志里抹掉。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):  # 格式化失败也不能让日志炸掉应用
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True


def setup_logging(level: str = "INFO") -> logging.Logger:
    """配置 rianvault logger：单 handler + 脱敏过滤器 + 不向上传播。"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False  # 不进 uvicorn 的 handler，避免重复
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [rianvault] %(message)s"))
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)
    for handler in logger.handlers:
        if not any(isinstance(f, SensitiveDataFilter) for f in handler.filters):
            handler.addFilter(SensitiveDataFilter())
    return logger
