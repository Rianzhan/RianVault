"""向量库 payload 红线：正文一个字都不许进 Qdrant。"""

from __future__ import annotations

import uuid

import pytest

from app.services import index_service


def test_payload_is_whitelisted() -> None:
    payload = index_service.build_payload(
        chunk_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        source_platform="chatgpt",
        source_model="gpt-4o",
        event_time=None,
    )
    assert set(payload) <= set(index_service.PAYLOAD_WHITELIST)
    assert payload["source_platform"] == "chatgpt"


def test_minimal_payload_drops_optional_metadata() -> None:
    from datetime import UTC, datetime

    payload = index_service.build_payload(
        chunk_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        source_platform="chatgpt",
        source_model="gpt-4o",
        event_time=datetime.now(UTC),
        minimal=True,
    )
    assert set(payload) == set(index_service.MINIMAL_PAYLOAD_KEYS)


@pytest.mark.parametrize("bad_key", ["content_text", "text", "body", "snippet"])
def test_body_fields_are_refused(bad_key: str) -> None:
    payload = {"chunk_id": "x", bad_key: "私人正文"}
    with pytest.raises(RuntimeError, match="正文类字段"):
        index_service._assert_payload_safe(payload)


def test_unknown_key_is_refused() -> None:
    with pytest.raises(RuntimeError, match="白名单外"):
        index_service._assert_payload_safe({"chunk_id": "x", "author_name": "Owner"})


def test_vector_id_is_deterministic() -> None:
    mid = uuid.uuid4()
    assert index_service.vector_id_for(mid, 0) == index_service.vector_id_for(mid, 0)
    assert index_service.vector_id_for(mid, 0) != index_service.vector_id_for(mid, 1)
    assert index_service.vector_id_for(mid, 0) != index_service.vector_id_for(uuid.uuid4(), 0)
