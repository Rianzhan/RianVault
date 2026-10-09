"""Importer adapter 协议。

核心数据模型只认 Canonical* 结构；任何来源格式（ChatGPT、Omate、ArenaAI…）
的细节都只允许存在于各自的 adapter 文件中。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class CanonicalMessage:
    source_message_id: str | None
    parent_source_message_id: str | None
    sort_order: int
    role: str  # user / assistant / system / tool / unknown
    content_text: str | None
    content_kind: str = "text"
    content_raw: dict | None = None
    event_time: datetime | None = None
    event_time_raw: str | None = None
    source_model: str | None = None
    source_model_note: str | None = None
    model_label_source: str | None = None  # export / manual（第一阶段无 inferred）
    dedup_hash: str = ""
    raw_metadata: dict = field(default_factory=dict)
    # 解析失败时：error 有值，本条进隔离区而不是 messages 表
    error: str | None = None
    error_raw: dict | None = None


@dataclass
class CanonicalConversation:
    source_conversation_id: str | None
    title: str | None
    source_platform: str
    raw_metadata: dict = field(default_factory=dict)
    dedup_hash: str | None = None  # 源会话 id 缺失时必填
    messages: list[CanonicalMessage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ImporterAdapter(Protocol):
    name: str  # 如 "chatgpt_export"
    version: str  # adapter 自身的版本，记入 imports.adapter_version

    def detect(self, data: bytes, filename: str) -> bool: ...

    def parse(self, data: bytes) -> Iterator[CanonicalConversation]: ...


def content_hash(*parts: str | None) -> str:
    """确定性内容哈希：无源 id 时的幂等兜底。输入 None 按空串处理。"""
    import hashlib

    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8", errors="replace"))
        h.update(b"\x1f")  # 字段分隔符，避免拼接歧义
    return h.hexdigest()
