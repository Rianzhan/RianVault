from conftest import read_fixture
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, ImportQuarantine, Message
from app.services.importers.pipeline import run_import


def _message_count(db: Session) -> int:
    return db.scalar(select(func.count(Message.id))) or 0


class TestChatGPTImport:
    def test_first_import_completed(self, db_session: Session) -> None:
        outcome = run_import(db_session, read_fixture("chatgpt_export_sample.json"), "a.json")
        imp = outcome.import_
        assert outcome.already_imported is False
        assert imp.status == "completed"
        stats = imp.stats
        assert stats["conversations_new"] == 1
        assert stats["imported"] == 4  # root 占位节点不入库
        assert stats["quarantined"] == 0
        # 对账不变式
        assert (
            stats["messages_parsed"]
            == stats["imported"] + stats["duplicates"] + stats["quarantined"]
        )

        conv = db_session.scalar(select(Conversation))
        assert conv.source_conversation_id == "conv-001"
        assert conv.started_at is not None and conv.started_at.year == 2023
        msgs = db_session.scalars(select(Message).order_by(Message.sort_order)).all()
        assert len(msgs) == 4
        assert [m.source_message_id for m in msgs] == [
            "msg-u1",
            "msg-a1",
            "msg-u2",
            "msg-a2",
        ]
        assert msgs[1].source_model == "gpt-4"
        assert msgs[3].raw_metadata["future_msg_field"] == {"x": 1}

    def test_reimport_same_file_idempotent(self, db_session: Session) -> None:
        data = read_fixture("chatgpt_export_sample.json")
        first = run_import(db_session, data, "a.json")
        second = run_import(db_session, data, "a.json")
        assert second.already_imported is True
        assert second.import_.id == first.import_.id
        assert _message_count(db_session) == 4

    def test_grown_export_imports_only_new_messages(self, db_session: Session) -> None:
        run_import(db_session, read_fixture("chatgpt_export_sample.json"), "a.json")
        outcome = run_import(db_session, read_fixture("chatgpt_export_grown.json"), "b.json")
        assert outcome.already_imported is False
        assert outcome.import_.status == "completed"
        stats = outcome.import_.stats
        assert stats["conversations_new"] == 0  # 会话复用
        assert stats["imported"] == 1  # 只有 msg-u3 是新的
        assert stats["duplicates"] == 4
        assert _message_count(db_session) == 5


class TestFailurePaths:
    def test_malformed_file_fails_loudly(self, db_session: Session) -> None:
        outcome = run_import(db_session, read_fixture("chatgpt_malformed.json"), "bad.json")
        imp = outcome.import_
        assert imp.status == "failed"
        assert imp.error is not None and "JSON" in imp.error
        assert _message_count(db_session) == 0

    def test_failed_import_can_be_retried(self, db_session: Session) -> None:
        data = read_fixture("chatgpt_malformed.json")
        first = run_import(db_session, data, "bad.json")
        second = run_import(db_session, data, "bad.json")
        # 失败的导入不享受 already_imported 短路；复用同一台账行重试
        assert second.already_imported is False
        assert second.import_.status == "failed"
        assert second.import_.id == first.import_.id


class TestJsonlImport:
    def test_quarantine_and_reconciliation(self, db_session: Session) -> None:
        outcome = run_import(db_session, read_fixture("rianvault_v1_sample.jsonl"), "s.jsonl")
        imp = outcome.import_
        assert imp.status == "completed"
        stats = imp.stats
        assert stats["imported"] == 4
        assert stats["quarantined"] == 1
        assert (
            stats["messages_parsed"]
            == stats["imported"] + stats["duplicates"] + stats["quarantined"]
        )
        quarantine = db_session.scalars(select(ImportQuarantine)).all()
        assert len(quarantine) == 1
        assert "role" in quarantine[0].reason or "text" in quarantine[0].reason
        assert quarantine[0].raw_payload  # 原始 payload 完整保留

    def test_jsonl_reimport_idempotent(self, db_session: Session) -> None:
        data = read_fixture("rianvault_v1_sample.jsonl")
        run_import(db_session, data, "s.jsonl")
        second = run_import(db_session, data, "s.jsonl")
        assert second.already_imported is True
        assert _message_count(db_session) == 4
