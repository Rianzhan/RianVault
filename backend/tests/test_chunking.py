"""切分测试：不改写正文、可还原、边界稳定。"""

from __future__ import annotations

import re

from app.services import chunking


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def test_short_message_is_single_chunk() -> None:
    chunks = chunking.chunk_message("m1", "c1", "今天我们聊了搬家的事。")
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].text == "今天我们聊了搬家的事。"


def test_empty_content_yields_no_chunks() -> None:
    assert chunking.chunk_message("m1", "c1", "") == []
    assert chunking.chunk_message("m1", "c1", "   \n  ") == []


def test_long_message_is_split_and_lossless() -> None:
    text = "。".join(f"第{i}段内容，讲的是我们那年夏天搬家的细节" for i in range(400))
    chunks = chunking.chunk_message("m1", "c1", text, max_tokens=120)
    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # 关键不变量：切分不许丢字
    assert _squash("".join(c.text for c in chunks)) == _squash(text)
    assert all(c.token_estimate <= 120 * 2 for c in chunks)  # 允许略超，不能失控


def test_oversized_single_sentence_is_hard_split() -> None:
    text = "啊" * 5000
    chunks = chunking.chunk_message("m1", "c1", text, max_tokens=100)
    assert len(chunks) > 1
    assert _squash("".join(c.text for c in chunks)) == _squash(text)


def test_token_estimate_is_monotonic() -> None:
    a = chunking.estimate_tokens("你好")
    b = chunking.estimate_tokens("你好，我们今天聊了很久关于搬家的各种细节与安排")
    assert a < b
    assert chunking.estimate_tokens("") == 0
