import pytest
from conftest import read_fixture

from app.services.importers.jsonl_v1 import JsonlV1Adapter


def _parse():
    adapter = JsonlV1Adapter()
    data = read_fixture("rianvault_v1_sample.jsonl")
    assert adapter.detect(data, "sample.jsonl")
    return list(adapter.parse(data))


class TestDetect:
    def test_accepts_jsonl_v1(self) -> None:
        assert JsonlV1Adapter().detect(read_fixture("rianvault_v1_sample.jsonl"), "sample.jsonl")

    def test_rejects_chatgpt_export(self) -> None:
        assert not JsonlV1Adapter().detect(
            read_fixture("chatgpt_export_sample.json"), "conversations.json"
        )


class TestParse:
    def test_good_and_bad_messages(self) -> None:
        (conv,) = _parse()
        assert conv.source_conversation_id == "om-100"
        assert conv.source_platform == "omate"
        good = [m for m in conv.messages if m.error is None]
        bad = [m for m in conv.messages if m.error is not None]
        assert len(good) == 4
        assert len(bad) == 1
        assert bad[0].error_raw is not None

    def test_sort_order_assigned(self) -> None:
        (conv,) = _parse()
        assert [m.sort_order for m in conv.messages] == [0, 1, 2, 3, 4]

    def test_naive_timestamp_warned_and_utc_assumed(self) -> None:
        (conv,) = _parse()
        m3 = next(m for m in conv.messages if m.source_message_id == "m3")
        assert m3.event_time is not None and m3.event_time.tzinfo is not None
        assert any("无时区" in w for w in conv.warnings)

    def test_missing_id_deterministic_hash(self) -> None:
        data = read_fixture("rianvault_v1_sample.jsonl")
        adapter = JsonlV1Adapter()
        first = [m for m in next(iter(adapter.parse(data))).messages if not m.source_message_id]
        second = [m for m in next(iter(adapter.parse(data))).messages if not m.source_message_id]
        good_first = [m for m in first if m.error is None]
        good_second = [m for m in second if m.error is None]
        assert good_first[0].dedup_hash == good_second[0].dedup_hash

    def test_model_fields(self) -> None:
        (conv,) = _parse()
        m2 = next(m for m in conv.messages if m.source_message_id == "m2")
        assert m2.source_model == "gpt-4o"
        assert m2.model_label_source == "export"

    def test_extra_preserved(self) -> None:
        (conv,) = _parse()
        assert conv.raw_metadata["origin"] == "fixture"

    def test_message_before_conversation_rejected(self) -> None:
        data = b'{"type":"message","conversation_id":"nope","role":"user","text":"x"}\n'
        with pytest.raises(ValueError, match="未声明"):
            list(JsonlV1Adapter().parse(data))
