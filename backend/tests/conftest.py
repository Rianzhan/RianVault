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
