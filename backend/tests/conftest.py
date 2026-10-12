import os

# 测试环境关闭全局限流：整套用例共用同一 client IP，会累积触发 429。
# 限流器本身在 tests/test_hardening.py 里有专门测试（用独立 app、真实配额）。
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "0")

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import ApiToken

FIXTURES = Path(__file__).parent / "fixtures"

OWNER_TOKEN = "rv-test-owner-token"
ZHAN_TOKEN = "rv-test-zhan-token"


def _seed_tokens(db: Session) -> None:
    for name, role, plaintext in (
        ("test-owner", "owner", OWNER_TOKEN),
        ("test-zhan", "zhan_mcp", ZHAN_TOKEN),
    ):
        db.add(
            ApiToken(
                id=uuid.uuid4(),
                name=name,
                role=role,
                token_hash=hash_token(plaintext),
            )
        )
    db.commit()


@pytest.fixture()
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSession() as session:
        _seed_tokens(session)
        yield session


def _make_client(db_session: Session, token: str | None) -> TestClient:
    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return TestClient(app, headers=headers)


@pytest.fixture()
def client(db_session: Session) -> Iterator[TestClient]:
    """默认 owner 身份。"""
    with _make_client(db_session, OWNER_TOKEN) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def zhan_client(db_session: Session) -> Iterator[TestClient]:
    with _make_client(db_session, ZHAN_TOKEN) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def anon_client(db_session: Session) -> Iterator[TestClient]:
    """无 token。"""
    with _make_client(db_session, None) as c:
        yield c
    app.dependency_overrides.clear()


def read_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture()
def seeded_stats(client: TestClient) -> dict:
    """导入一个会话 + 一条带 span 的记忆，供统计/前端接口测试复用。"""
    with open("tests/fixtures/chatgpt_export_sample.json", "rb") as f:
        r = client.post("/api/imports", files={"file": ("c.json", f)})
    assert r.status_code == 200, r.text
    conv = client.get("/api/conversations").json()[0]
    msgs = client.get(f"/api/conversations/{conv['id']}/messages").json()
    memory = client.post(
        "/api/memories",
        json={
            "title": "统计用记忆",
            "body": "用于统计接口的样本。",
            "memory_type": "note",
            "event_time_start": "2023-11-14",
        },
    ).json()
    client.post(
        f"/api/memories/{memory['id']}/spans",
        json={
            "conversation_id": conv["id"],
            "start_message_id": msgs[0]["id"],
            "end_message_id": msgs[-1]["id"],
            "span_type": "evidence",
        },
    )
    return {"conversation": conv, "messages": msgs, "memory": memory}
