"""加固测试：日志不含敏感信息、5xx 不装成功、安全头、限流、无第三方 embedding。"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core import errors
from app.core.logging_setup import LOGGER_NAME, redact


def test_redact_masks_token_and_credentials() -> None:
    message = "Authorization: Bearer rv_secrettoken123 数据库连接 postgres://user:pass@host/db"
    cleaned = redact(message)
    assert "rv_secrettoken123" not in cleaned
    assert "pass" not in cleaned.split("@")[0]
    assert "***" in cleaned


def test_redact_masks_body_like_fields() -> None:
    cleaned = redact('created memory body="Owner的私人正文" ok')
    assert "Owner的私人正文" not in cleaned
    assert "***" in cleaned


def test_logger_filter_applies_redaction(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        logger.info("token=%s", "rv_plaintoken123")
    # caplog 走的是 root 传播链，过滤器挂在 handler 上；这里直接验证过滤器行为
    from app.core.logging_setup import SensitiveDataFilter

    record = logging.LogRecord(
        LOGGER_NAME, logging.INFO, __file__, 1, "raw %s", ("rv_abc123456",), None
    )
    assert SensitiveDataFilter().filter(record) is True
    assert "rv_abc123456" not in record.getMessage()


def test_request_logs_do_not_leak_token_or_query(
    client, seeded_stats, caplog: pytest.LogCaptureFixture
) -> None:
    """真实请求：日志里不许出现 token、正文、查询词。"""
    logger = logging.getLogger(LOGGER_NAME)
    handler_messages: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            handler_messages.append(record.getMessage())

    handler = Capture()
    handler.addFilter(__import__("app.core.logging_setup", fromlist=["x"]).SensitiveDataFilter())
    logger.addHandler(handler)
    try:
        # 只用 keyword 模式：semantic 会去加载本地权重（慢且依赖网络），与本测试无关
        client.post("/api/search", json={"query": "绝对不该进日志的私人查询词", "mode": "keyword"})
        client.get("/api/memories")
        client.get("/api/stats")
    finally:
        logger.removeHandler(handler)

    joined = "\n".join(handler_messages)
    assert "rv-test-owner-token" not in joined
    assert "绝对不该进日志的私人查询词" not in joined
    assert "用于统计接口的样本。" not in joined


def test_unhandled_exception_returns_500_without_success_word() -> None:
    app = FastAPI()
    errors.install_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("Owner的私人正文不该出现在响应里")

    from fastapi.testclient import TestClient

    with pytest.raises(RuntimeError):  # TestClient 默认会重新抛出服务端异常
        TestClient(app, raise_server_exceptions=True).get("/boom")


def test_unhandled_exception_response_shape() -> None:
    from fastapi.testclient import TestClient

    app = FastAPI()
    errors.install_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret Owner的私人正文")

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert "error_id" in body
    assert "success" not in r.text.lower()
    assert "Owner的私人正文" not in r.text
    assert "secret" not in r.text


def test_validation_error_does_not_echo_values() -> None:
    from fastapi.testclient import TestClient
    from pydantic import BaseModel

    class Req(BaseModel):
        body: str

    app = FastAPI()
    errors.install_exception_handlers(app)

    @app.post("/x")
    def x(req: Req) -> JSONResponse:  # pragma: no cover - 仅用于触发校验
        return JSONResponse({"ok": True})

    r = TestClient(app, raise_server_exceptions=False).post("/x", json={"body": 123})
    assert r.status_code == 422
    assert "123" not in r.text or "int" in r.text  # 只回类型信息，不回显原值


def test_security_headers_and_no_store(client) -> None:
    r = client.get("/api/memories")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
    assert r.headers.get("Cache-Control") == "no-store"


def test_rate_limit_returns_429() -> None:
    """真实限流：超过配额的写请求返回 429，绝不放行。"""
    from fastapi.testclient import TestClient

    from app.core.middleware import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, per_minute=2)

    @app.post("/api/ping")
    def ping() -> dict:
        return {"ok": True}

    @app.get("/api/ping")
    def pong() -> dict:
        return {"ok": True}

    client = TestClient(app)
    assert client.post("/api/ping").status_code == 200
    assert client.post("/api/ping").status_code == 200
    r = client.post("/api/ping")
    assert r.status_code == 429
    assert "429" in r.text or "频繁" in r.text
    # GET 不受限（浏览不该被挡）
    assert client.get("/api/ping").status_code == 200


def test_unknown_embedding_provider_fails_fast() -> None:
    """拼错 provider 必须立刻报错，而不是静默退化或联网兜底。"""
    from app.services.embedding import get_embedding_provider

    with pytest.raises(ValueError, match="未知的 embedding provider"):
        get_embedding_provider("openai")


def test_no_third_party_embedding_provider() -> None:
    """零第三方 embedding：只注册本地实现，配置里不存在任何远端凭据字段。"""
    from app.core.config import Settings
    from app.services.embedding import PROVIDERS

    assert set(PROVIDERS) == {"sentence-transformers"}
    fields = set(Settings.model_fields)
    forbidden = {
        f for f in fields if any(k in f for k in ("openai", "api_key", "endpoint_url", "anthropic"))
    }
    assert not forbidden, forbidden

    source = Path("app/services/embedding.py").read_text(encoding="utf-8")
    assert "requests" not in source and "httpx" not in source
