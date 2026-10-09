import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Conversation, Import, Message


def _make_import(db: Session) -> Import:
    imp = Import(
        id=uuid.uuid4(),
        source_type="chatgpt_export",
        original_filename="t.json",
        checksum_sha256=uuid.uuid4().hex,
        file_size_bytes=1,
        adapter_version="1.0.0",
        status="running",
        stats={},
        warnings=[],
    )
    db.add(imp)
    return imp


def _make_conversation(db: Session, imp: Import, source_id: str = "c-1") -> Conversation:
    conv = Conversation(
        id=uuid.uuid4(),
        source_platform="chatgpt",
        source_conversation_id=source_id,
        title="t",
        import_id=imp.id,
        raw_metadata={"k": "v"},
    )
    db.add(conv)
    return conv


def _make_message(db: Session, conv: Conversation, imp: Import, **kw) -> Message:
    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        sort_order=kw.get("sort_order", 0),
        role=kw.get("role", "user"),
        content_text=kw.get("content_text", "hi"),
        source_message_id=kw.get("source_message_id"),
        import_id=imp.id,
        dedup_hash=kw.get("dedup_hash", uuid.uuid4().hex),
        event_time=kw.get("event_time"),
        raw_metadata={},
    )
    db.add(msg)
    return msg


class TestUniqueConstraints:
    def test_conversation_source_unique(self, db_session: Session) -> None:
        imp = _make_import(db_session)
        _make_conversation(db_session, imp, source_id="dup")
        _make_conversation(db_session, imp, source_id="dup")
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_message_source_id_unique(self, db_session: Session) -> None:
        imp = _make_import(db_session)
        conv = _make_conversation(db_session, imp)
        _make_message(db_session, conv, imp, source_message_id="m-1")
        _make_message(db_session, conv, imp, source_message_id="m-1", sort_order=1)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_message_dedup_hash_unique(self, db_session: Session) -> None:
        imp = _make_import(db_session)
        conv = _make_conversation(db_session, imp)
        _make_message(db_session, conv, imp, dedup_hash="h-1")
        _make_message(db_session, conv, imp, dedup_hash="h-1", sort_order=1)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_null_source_message_id_allowed_multiple(self, db_session: Session) -> None:
        imp = _make_import(db_session)
        conv = _make_conversation(db_session, imp)
        _make_message(db_session, conv, imp, source_message_id=None)
        _make_message(db_session, conv, imp, source_message_id=None, sort_order=1)
        db_session.commit()  # 不抛异常即通过


class TestTimeSeparation:
    def test_event_time_distinct_from_ingested_at(self, db_session: Session) -> None:
        imp = _make_import(db_session)
        conv = _make_conversation(db_session, imp)
        happened = datetime(2025, 3, 14, 13, 2, 11, tzinfo=UTC)
        msg = _make_message(db_session, conv, imp, event_time=happened)
        db_session.commit()
        assert msg.event_time == happened
        assert msg.ingested_at is not None
        assert msg.ingested_at.year >= 2026  # 导入时间由系统记录，与事情发生时间分离


class TestRawMetadata:
    def test_json_roundtrip(self, db_session: Session) -> None:
        imp = _make_import(db_session)
        conv = _make_conversation(db_session, imp)
        db_session.commit()
        assert conv.raw_metadata == {"k": "v"}
