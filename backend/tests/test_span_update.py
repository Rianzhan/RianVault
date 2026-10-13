"""改来源片段的起止范围：可改、可回溯、乱改要被拒。"""

import uuid

import pytest


@pytest.fixture()
def with_span(client):
    """导入一个会话，建一条记忆并绑一条 span（范围 = 第 1→2 条）。"""
    with open("tests/fixtures/chatgpt_export_sample.json", "rb") as f:
        r = client.post("/api/imports", files={"file": ("c.json", f)})
    assert r.status_code == 200, r.text
    conv = client.get("/api/conversations").json()[0]
    msgs = client.get(f"/api/conversations/{conv['id']}/messages").json()
    memory = client.post(
        "/api/memories",
        json={"title": "改范围用", "body": "原文范围需要修正。", "memory_type": "note"},
    ).json()
    span = client.post(
        f"/api/memories/{memory['id']}/spans",
        json={
            "conversation_id": conv["id"],
            "start_message_id": msgs[0]["id"],
            "end_message_id": msgs[1]["id"],
            "span_type": "evidence",
        },
    )
    assert span.status_code == 200, span.text
    return {
        "conversation": conv,
        "messages": msgs,
        "memory": memory,
        "span": span.json(),
    }


def test_update_span_range(client, with_span) -> None:
    msgs = with_span["messages"]
    r = client.request(
        "PATCH",
        f"/api/memories/{with_span['memory']['id']}/spans/{with_span['span']['id']}",
        json={"start_message_id": msgs[1]["id"], "end_message_id": msgs[3]["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["start_message_id"] == msgs[1]["id"]
    assert body["end_message_id"] == msgs[3]["id"]


def test_update_span_bumps_version(client, with_span) -> None:
    msgs = with_span["messages"]
    mem_id = with_span["memory"]["id"]
    # 建记忆时是 v1，绑 span 后已经是 v2：以改范围前的实际版本为准
    before = client.get(f"/api/memories/{mem_id}").json()["memory"]["current_version"]
    client.request(
        "PATCH",
        f"/api/memories/{with_span['memory']['id']}/spans/{with_span['span']['id']}",
        json={"end_message_id": msgs[2]["id"]},
    )
    detail = client.get(f"/api/memories/{with_span['memory']['id']}").json()
    assert detail["memory"]["current_version"] == before + 1
    # 旧范围仍留在旧版本快照里（可回滚）
    old = next(v for v in detail["versions"] if v["version_number"] == before)
    assert old["snapshot"]["spans"][0]["end_message_id"] == with_span["span"]["end_message_id"]


def test_update_span_snapshot_shows_new_range(client, with_span) -> None:
    msgs = with_span["messages"]
    mem_id = with_span["memory"]["id"]
    client.request(
        "PATCH",
        f"/api/memories/{mem_id}/spans/{with_span['span']['id']}",
        json={"end_message_id": msgs[2]["id"]},
    )
    detail = client.get(f"/api/memories/{mem_id}").json()
    latest = max(detail["versions"], key=lambda v: v["version_number"])
    assert latest["snapshot"]["spans"][0]["end_message_id"] == msgs[2]["id"]


def test_update_span_records_before_after_in_audit(client, with_span) -> None:
    msgs = with_span["messages"]
    client.request(
        "PATCH",
        f"/api/memories/{with_span['memory']['id']}/spans/{with_span['span']['id']}",
        json={"start_message_id": msgs[0]["id"], "end_message_id": msgs[2]["id"]},
    )
    events = client.get(f"/api/memories/{with_span['memory']['id']}/audit").json()
    updated = [e for e in events if e["event_type"] == "span_updated"]
    assert len(updated) == 1
    detail = updated[0]["detail"]
    assert detail["before"]["end_message_id"] == with_span["span"]["end_message_id"]
    assert detail["after"]["end_message_id"] == msgs[2]["id"]
    # 审计只记 id，不记正文
    assert "content_text" not in str(detail)


def test_update_span_rejects_reversed_order(client, with_span) -> None:
    msgs = with_span["messages"]
    r = client.request(
        "PATCH",
        f"/api/memories/{with_span['memory']['id']}/spans/{with_span['span']['id']}",
        json={"start_message_id": msgs[3]["id"], "end_message_id": msgs[1]["id"]},
    )
    assert r.status_code == 400, r.text


def test_update_span_rejects_message_from_other_conversation(client, with_span, db_session) -> None:
    """拿别的会话的消息来改范围 = 换出处，必须拒绝。"""
    from sqlalchemy import select

    from app.models import Conversation, Message

    import_id = db_session.scalar(select(Conversation.import_id).limit(1))
    other_conv = Conversation(
        source_platform="chatgpt",
        source_conversation_id="conv-other",
        title="另一个会话",
        import_id=import_id,
    )
    db_session.add(other_conv)
    db_session.flush()
    import hashlib

    other_msg = Message(
        conversation_id=other_conv.id,
        sort_order=1,
        role="user",
        content_text="别的会话的消息",
        content_kind="text",
        import_id=other_conv.import_id,
        dedup_hash=hashlib.sha256(b"other-conv-msg-1").hexdigest(),
    )
    db_session.add(other_msg)
    db_session.commit()

    r = client.request(
        "PATCH",
        f"/api/memories/{with_span['memory']['id']}/spans/{with_span['span']['id']}",
        json={"start_message_id": str(other_msg.id)},
    )
    assert r.status_code == 400, r.text


def test_update_missing_span_returns_404(client, with_span) -> None:
    r = client.request(
        "PATCH",
        f"/api/memories/{with_span['memory']['id']}/spans/{uuid.uuid4()}",
        json={"end_message_id": with_span["messages"][2]["id"]},
    )
    assert r.status_code == 404, r.text


def test_update_span_requires_token(anon_client, with_span) -> None:
    r = anon_client.request(
        "PATCH",
        f"/api/memories/{with_span['memory']['id']}/spans/{with_span['span']['id']}",
        json={},
    )
    assert r.status_code == 401


def test_zhan_can_update_span(zhan_client, with_span) -> None:
    """权限矩阵：zhan 可以写来源（含改范围），不能删/恢复。"""
    msgs = with_span["messages"]
    r = zhan_client.request(
        "PATCH",
        f"/api/memories/{with_span['memory']['id']}/spans/{with_span['span']['id']}",
        json={"end_message_id": msgs[2]["id"]},
    )
    assert r.status_code == 200, r.text
