"""T3 领域测试：版本史、spans、审计、恢复、软删除。"""

import uuid
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models import Conversation, Import, Message
from app.services import audit_service, memory_service, span_service
from app.services.memory_service import MemoryValidationError


def _build_conv_with_messages(db_session: Session) -> tuple[Conversation, list[Message]]:
    imp = Import(
        id=uuid.uuid4(),
        source_type="jsonl_v1",
        original_filename="t.jsonl",
        checksum_sha256=uuid.uuid4().hex,
        file_size_bytes=1,
        adapter_version="1.0.0",
        status="completed",
        stats={},
        warnings=[],
    )
    conv = Conversation(
        id=uuid.uuid4(),
        source_platform="omate",
        source_conversation_id=uuid.uuid4().hex[:12],
        title="t",
        import_id=imp.id,
        raw_metadata={},
    )
    db_session.add_all([imp, conv])
    db_session.flush()
    msgs = [
        Message(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            source_message_id=f"m{i}",
            sort_order=i,
            role="user" if i % 2 == 0 else "assistant",
            content_text=f"消息 {i}",
            import_id=imp.id,
            dedup_hash=f"h-{conv.id}-{i}",
            raw_metadata={},
        )
        for i in range(6)
    ]
    db_session.add_all(msgs)
    db_session.commit()
    return conv, msgs


@pytest.fixture()
def make_conv(db_session: Session):
    """工厂 fixture：可调用多次，每次创建一个新会话。"""
    return lambda: _build_conv_with_messages(db_session)


@pytest.fixture()
def conv_with_messages(make_conv) -> tuple[Conversation, list[Message]]:
    return make_conv()


def _mk(db: Session, **kw) -> object:
    defaults = {"body": "Owner喜欢安静的空间。", "actor": "owner"}
    defaults.update(kw)
    return memory_service.create_memory(db, **defaults)


class TestCreateAndVersion:
    def test_create_makes_v1_snapshot_and_audit(self, db_session: Session) -> None:
        memory = _mk(db_session, actor_model="gpt-5.6-sol")
        assert memory.current_version == 1
        versions = memory_service.list_versions(db_session, memory.id)
        assert len(versions) == 1
        snap = versions[0].snapshot
        assert snap["body"] == "Owner喜欢安静的空间。"
        assert snap["spans"] == []
        assert versions[0].edited_by_actor == "owner"
        assert versions[0].edited_by_model == "gpt-5.6-sol"
        events = audit_service.list_for_target(db_session, "memory", memory.id)
        assert [e.event_type for e in events] == ["memory_created"]

    def test_event_dates_use_date_granularity(self, db_session: Session) -> None:
        memory = _mk(
            db_session,
            event_time_start=date(2025, 3, 14),
            event_time_end=date(2025, 3, 15),
        )
        assert memory.event_time_start == date(2025, 3, 14)
        assert memory.created_at.year >= 2026  # 发生时间 vs 创建时间分离

    def test_create_validation(self, db_session: Session) -> None:
        with pytest.raises(MemoryValidationError):
            _mk(db_session, body="   ")
        with pytest.raises(MemoryValidationError):
            _mk(db_session, memory_type="bogus")
        with pytest.raises(MemoryValidationError):
            _mk(
                db_session,
                event_time_start=date(2025, 5, 1),
                event_time_end=date(2025, 3, 1),
            )


class TestUpdate:
    def test_update_bumps_version_with_full_snapshot(self, db_session: Session) -> None:
        memory = _mk(db_session)
        memory_service.update_memory(
            db_session,
            memory.id,
            actor="zhan_mcp",
            actor_model="kimi-k3",
            body="Owner喜欢安静、有空间感的家。",
            reason="补充细节",
        )
        assert memory.current_version == 2
        versions = memory_service.list_versions(db_session, memory.id)
        assert len(versions) == 2
        assert versions[1].snapshot["body"] == "Owner喜欢安静、有空间感的家。"
        assert versions[1].edited_by_actor == "zhan_mcp"
        assert versions[1].edit_reason == "补充细节"
        # 旧版本不被改写
        assert versions[0].snapshot["body"] == "Owner喜欢安静的空间。"

    def test_noop_update_makes_no_version(self, db_session: Session) -> None:
        memory = _mk(db_session)
        memory_service.update_memory(
            db_session, memory.id, actor="owner", body="Owner喜欢安静的空间。"
        )
        assert memory.current_version == 1

    def test_updated_event_fields_audited(self, db_session: Session) -> None:
        memory = _mk(db_session)
        memory_service.update_memory(
            db_session,
            memory.id,
            actor="owner",
            title="居住偏好",
            tags=["home", "space"],
        )
        events = audit_service.list_for_target(db_session, "memory", memory.id)
        updated = [e for e in events if e.event_type == "memory_updated"]
        assert updated[0].detail["changed_fields"] == ["title", "tags"]


class TestSpans:
    def test_add_span_creates_new_version(self, db_session: Session, conv_with_messages) -> None:
        conv, msgs = conv_with_messages
        memory = _mk(db_session)
        span = span_service.add_span(
            db_session,
            memory.id,
            conversation_id=conv.id,
            start_message_id=msgs[1].id,
            end_message_id=msgs[3].id,
            span_type="evidence",
            actor="zhan_mcp",
        )
        assert memory.current_version == 2  # span 增删也触发新版本
        versions = memory_service.list_versions(db_session, memory.id)
        snap_spans = versions[1].snapshot["spans"]
        assert len(snap_spans) == 1
        assert snap_spans[0]["span_type"] == "evidence"
        events = audit_service.list_for_target(db_session, "memory", memory.id)
        assert events[-1].event_type == "span_added"
        assert span.span_type == "evidence"

    def test_multiple_spans_cross_conversation(self, db_session: Session, make_conv) -> None:
        conv1, msgs1 = make_conv()
        conv2, msgs2 = make_conv()  # 第二个会话
        assert conv1.id != conv2.id
        memory = _mk(db_session)
        span_service.add_span(
            db_session,
            memory.id,
            conversation_id=conv1.id,
            start_message_id=msgs1[0].id,
            end_message_id=msgs1[1].id,
            span_type="evidence",
            actor="owner",
            sort_order=0,
        )
        span_service.add_span(
            db_session,
            memory.id,
            conversation_id=conv2.id,
            start_message_id=msgs2[4].id,
            end_message_id=msgs2[5].id,
            span_type="context",
            actor="owner",
            sort_order=1,
        )
        spans = memory_service.active_spans(db_session, memory.id)
        assert len(spans) == 2
        assert {s.span_type for s in spans} == {"evidence", "context"}
        assert len({s.conversation_id for s in spans}) == 2  # 跨会话

    def test_span_validation(self, db_session: Session, make_conv) -> None:
        conv, msgs = make_conv()
        conv2, _ = make_conv()
        memory = _mk(db_session)
        # 反向范围
        with pytest.raises(MemoryValidationError, match="不晚于"):
            span_service.add_span(
                db_session,
                memory.id,
                conversation_id=conv.id,
                start_message_id=msgs[3].id,
                end_message_id=msgs[1].id,
                span_type="evidence",
                actor="owner",
            )
        # 消息不属于指定会话
        with pytest.raises(MemoryValidationError, match="属于指定的 conversation"):
            span_service.add_span(
                db_session,
                memory.id,
                conversation_id=conv2.id,
                start_message_id=msgs[1].id,
                end_message_id=msgs[2].id,
                span_type="evidence",
                actor="owner",
            )
        # 非法类型
        with pytest.raises(MemoryValidationError, match="evidence 或 context"):
            span_service.add_span(
                db_session,
                memory.id,
                conversation_id=conv.id,
                start_message_id=msgs[1].id,
                end_message_id=msgs[2].id,
                span_type="proof",
                actor="owner",
            )
        # 不存在的消息
        with pytest.raises(MemoryValidationError, match="不存在"):
            span_service.add_span(
                db_session,
                memory.id,
                conversation_id=conv.id,
                start_message_id=uuid.uuid4(),
                end_message_id=msgs[2].id,
                span_type="evidence",
                actor="owner",
            )
        assert memory.current_version == 1  # 失败不产生版本

    def test_remove_span_soft_with_version(self, db_session: Session, conv_with_messages) -> None:
        conv, msgs = conv_with_messages
        memory = _mk(db_session)
        span = span_service.add_span(
            db_session,
            memory.id,
            conversation_id=conv.id,
            start_message_id=msgs[0].id,
            end_message_id=msgs[2].id,
            span_type="context",
            actor="owner",
        )
        span_service.remove_span(db_session, span.id, actor="owner")
        assert memory.current_version == 3
        assert memory_service.active_spans(db_session, memory.id) == []
        events = audit_service.list_for_target(db_session, "memory", memory.id)
        assert [e.event_type for e in events] == [
            "memory_created",
            "span_added",
            "span_removed",
        ]


class TestDeleteAndRestore:
    def test_soft_delete(self, db_session: Session) -> None:
        memory = _mk(db_session)
        memory_service.soft_delete_memory(db_session, memory.id, actor="owner")
        assert memory.status == "deleted"
        assert memory.deleted_at is not None
        assert memory.current_version == 2
        # 已删除不能再编辑
        with pytest.raises(MemoryValidationError, match="已删除"):
            memory_service.update_memory(db_session, memory.id, actor="owner", body="x")

    def test_restore_appends_new_version(self, db_session: Session, conv_with_messages) -> None:
        conv, msgs = conv_with_messages
        memory = _mk(db_session, body="原始内容")
        span_service.add_span(
            db_session,
            memory.id,
            conversation_id=conv.id,
            start_message_id=msgs[0].id,
            end_message_id=msgs[1].id,
            span_type="evidence",
            actor="owner",
        )
        memory_service.update_memory(db_session, memory.id, actor="owner", body="被改坏的内容")
        assert memory.current_version == 3

        memory_service.restore_version(db_session, memory.id, 2, actor="owner", reason="回滚误改")
        assert memory.current_version == 4  # 恢复 = 追加新版本
        assert memory.body == "原始内容"
        spans = memory_service.active_spans(db_session, memory.id)
        assert len(spans) == 1  # v2 快照里的 span 被重建
        versions = memory_service.list_versions(db_session, memory.id)
        assert len(versions) == 4
        assert versions[3].snapshot["spans"][0]["span_type"] == "evidence"
        events = audit_service.list_for_target(db_session, "memory", memory.id)
        assert events[-1].event_type == "version_restored"
        assert events[-1].detail["restored_from"] == 2

    def test_restore_unknown_version_404(self, db_session: Session) -> None:
        memory = _mk(db_session)
        with pytest.raises(LookupError):
            memory_service.restore_version(db_session, memory.id, 99, actor="owner")

    def test_undelete_goes_back_to_the_status_before_deletion(self, db_session: Session) -> None:
        """回收站还原不能把「归档」悄悄变成「活跃」——要还原到删之前那个状态。"""
        memory = _mk(db_session)
        # 走正常通道归档（会留版本快照），而不是硬改字段
        memory_service.update_memory(db_session, memory.id, actor="owner", status="archived")
        assert memory.status == "archived"

        memory_service.soft_delete_memory(db_session, memory.id, actor="owner")
        assert memory.status == "deleted"

        memory_service.undelete_memory(db_session, memory.id, actor="owner")
        assert memory.status == "archived"
        assert memory.deleted_at is None

    def test_undelete_appends_version_and_audits(self, db_session: Session) -> None:
        memory = _mk(db_session)
        memory_service.soft_delete_memory(db_session, memory.id, actor="owner")
        before = memory.current_version

        memory_service.undelete_memory(db_session, memory.id, actor="owner", reason="误删")
        assert memory.current_version == before + 1  # 还原也是追加版本，不改写历史

        versions = memory_service.list_versions(db_session, memory.id)
        assert len(versions) == memory.current_version
        events = audit_service.list_for_target(db_session, "memory", memory.id)
        assert events[-1].event_type == "memory_restored"
        assert events[-1].detail["restored_to"] == "active"

    def test_undelete_of_a_live_memory_is_a_noop(self, db_session: Session) -> None:
        memory = _mk(db_session)
        memory_service.undelete_memory(db_session, memory.id, actor="owner")
        assert memory.current_version == 1  # 没删过就不该产生新版本


class TestInvariants:
    def test_versions_count_equals_current_version(
        self, db_session: Session, conv_with_messages
    ) -> None:
        conv, msgs = conv_with_messages
        memory = _mk(db_session)
        memory_service.update_memory(db_session, memory.id, actor="owner", title="t")
        span_service.add_span(
            db_session,
            memory.id,
            conversation_id=conv.id,
            start_message_id=msgs[0].id,
            end_message_id=msgs[0].id,
            span_type="evidence",
            actor="owner",
        )
        span = memory_service.active_spans(db_session, memory.id)[0]
        span_service.remove_span(db_session, span.id, actor="owner")
        memory_service.soft_delete_memory(db_session, memory.id, actor="owner")
        versions = memory_service.list_versions(db_session, memory.id)
        assert len(versions) == memory.current_version == 5
