import json

from conftest import read_fixture

from app.services.importers.chatgpt import ChatGPTExportAdapter


def _parse():
    adapter = ChatGPTExportAdapter()
    data = read_fixture("chatgpt_export_sample.json")
    assert adapter.detect(data, "conversations.json")
    return list(adapter.parse(data))


class TestDetect:
    def test_accepts_chatgpt_export(self) -> None:
        assert ChatGPTExportAdapter().detect(
            read_fixture("chatgpt_export_sample.json"), "conversations.json"
        )

    def test_rejects_other_formats(self) -> None:
        adapter = ChatGPTExportAdapter()
        assert not adapter.detect(read_fixture("broken.json"), "broken.json")
        assert not adapter.detect(read_fixture("rianvault_v1_sample.jsonl"), "sample.jsonl")


class TestLinearization:
    def test_current_branch_only_placeholder_marked(self) -> None:
        (conv,) = _parse()
        # 主时间线 5 个节点：root 占位 + 4 条真实消息；alt 分支不进主时间线
        assert len(conv.messages) == 5
        placeholder = conv.messages[0]
        assert placeholder.raw_metadata.get("placeholder") is True
        real = conv.messages[1:]
        assert [m.source_message_id for m in real] == [
            "msg-u1",
            "msg-a1",
            "msg-u2",
            "msg-a2",
        ]
        assert all(m.source_message_id != "msg-a1-alt" for m in real)

    def test_parent_links_preserved(self) -> None:
        (conv,) = _parse()
        by_id = {m.source_message_id: m for m in conv.messages if m.source_message_id}
        assert by_id["msg-a1"].parent_source_message_id == "n-u1"


class TestModelAndContent:
    def test_model_slug_exported(self) -> None:
        (conv,) = _parse()
        by_id = {m.source_message_id: m for m in conv.messages if m.source_message_id}
        assert by_id["msg-a1"].source_model == "gpt-4"
        assert by_id["msg-a2"].source_model == "gpt-4o"
        assert by_id["msg-a1"].model_label_source == "export"
        assert by_id["msg-u1"].source_model is None

    def test_multimodal_text_extracted_with_warning(self) -> None:
        (conv,) = _parse()
        u2 = next(m for m in conv.messages if m.source_message_id == "msg-u2")
        assert u2.content_kind == "multimodal"
        assert u2.content_text == "给我讲讲记忆。"
        assert any("multimodal" in w for w in conv.warnings)

    def test_event_time_parsed_and_raw_kept(self) -> None:
        (conv,) = _parse()
        u1 = next(m for m in conv.messages if m.source_message_id == "msg-u1")
        assert u1.event_time is not None and u1.event_time.year == 2023
        assert u1.event_time_raw == repr(1700000001.0)


class TestNothingSilentlyDropped:
    def test_unknown_conversation_field_preserved_and_warned(self) -> None:
        (conv,) = _parse()
        assert conv.raw_metadata["future_field_xyz"] is True
        assert any("future_field_xyz" in w for w in conv.warnings)

    def test_unknown_message_field_preserved(self) -> None:
        (conv,) = _parse()
        a2 = next(m for m in conv.messages if m.source_message_id == "msg-a2")
        assert a2.raw_metadata["future_msg_field"] == {"x": 1}


class TestMissingIds:
    def test_missing_message_id_deterministic_hash(self) -> None:
        conv = {
            "id": "c-x",
            "title": "t",
            "mapping": {
                "n1": {
                    "id": "n1",
                    "message": {
                        "author": {"role": "user"},
                        "create_time": 1700000001.0,
                        "content": {"content_type": "text", "parts": ["无 id 消息"]},
                    },
                    "parent": None,
                    "children": [],
                }
            },
            "current_node": "n1",
        }
        adapter = ChatGPTExportAdapter()
        data = json.dumps([conv]).encode()
        first = next(iter(adapter.parse(data))).messages[0]
        second = next(iter(adapter.parse(data))).messages[0]
        assert first.source_message_id is None
        assert first.dedup_hash == second.dedup_hash
