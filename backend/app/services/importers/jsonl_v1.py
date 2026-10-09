"""规范化 JSONL v1 (rianvault-jsonl-v1) adapter。

规范见 docs/import-format-v1.md。这是以后 Omate / ArenaAI / Cakumi / API 酒馆
等来源的统一落地格式；它们也可以以后写自己的 adapter，但 JSONL v1 是最低门槛。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime

from app.services.importers.base import (
    CanonicalConversation,
    CanonicalMessage,
    content_hash,
)

FORMAT_TAG = "rianvault-jsonl-v1"


class JsonlV1Adapter:
    name = "jsonl_v1"
    version = "1.0.0"

    def detect(self, data: bytes, filename: str) -> bool:
        for line in data.splitlines()[:20]:
            line = line.strip()
            if not line:
                continue
            if b"rianvault-jsonl-v1" in line:
                return True
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return False
            return isinstance(obj, dict) and obj.get("format") == FORMAT_TAG
        return False

    def parse(self, data: bytes) -> Iterator[CanonicalConversation]:
        conversations: dict[str, CanonicalConversation] = {}
        order: list[str] = []
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValueError(f"JSONL 不是合法 UTF-8: {e}") from e

        for lineno, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"第 {lineno} 行不是合法 JSON: {e}") from e
            if not isinstance(obj, dict):
                raise TypeError(f"第 {lineno} 行应为 JSON 对象")

            line_type = obj.get("type")
            if line_type == "conversation":
                conv_id = obj.get("conversation_id")
                if not conv_id:
                    raise ValueError(f"第 {lineno} 行 conversation 缺少 conversation_id")
                conv_id = str(conv_id)
                conv = CanonicalConversation(
                    source_conversation_id=conv_id,
                    title=obj.get("title"),
                    source_platform=str(obj.get("platform") or "unknown"),
                    raw_metadata=dict(obj.get("extra") or {}),
                )
                conversations[conv_id] = conv
                order.append(conv_id)
            elif line_type == "message":
                conv_id = obj.get("conversation_id")
                if not conv_id or str(conv_id) not in conversations:
                    raise ValueError(
                        f"第 {lineno} 行 message 引用了未声明的 conversation_id: {conv_id!r}"
                    )
                conv = conversations[str(conv_id)]
                conv.messages.append(self._parse_message(obj, conv, lineno))
            else:
                raise ValueError(f"第 {lineno} 行未知 type: {line_type!r}")

        for conv_id in order:
            conv = conversations[conv_id]
            for idx, msg in enumerate(conv.messages):
                if msg.sort_order == -1:
                    msg.sort_order = idx
            yield conv

    # ------------------------------------------------------------------

    def _parse_message(
        self, obj: dict, conv: CanonicalConversation, lineno: int
    ) -> CanonicalMessage:
        role = obj.get("role")
        text = obj.get("text")
        if (not role) or (text is None and not obj.get("content_raw")):
            return CanonicalMessage(
                source_message_id=None,
                parent_source_message_id=None,
                sort_order=-1,
                role=str(role or "unknown"),
                content_text=None,
                dedup_hash=content_hash(conv.source_conversation_id, str(lineno)),
                error=f"第 {lineno} 行缺少 role 或 text",
                error_raw=obj,
            )

        ts = obj.get("timestamp")
        event_time = None
        event_time_raw = None
        if isinstance(ts, str) and ts:
            event_time_raw = ts
            try:
                event_time = datetime.fromisoformat(ts)
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=UTC)
                    conv.warnings.append(f"第 {lineno} 行时间戳无时区，已按 UTC 处理")
            except ValueError:
                conv.warnings.append(f"第 {lineno} 行时间戳无法解析: {ts!r}")

        source_message_id = obj.get("message_id")
        model = obj.get("model")
        return CanonicalMessage(
            source_message_id=str(source_message_id) if source_message_id else None,
            parent_source_message_id=(str(obj["parent_id"]) if obj.get("parent_id") else None),
            sort_order=-1,
            role=str(role),
            content_text=text,
            content_kind=str(obj.get("content_kind") or "text"),
            content_raw=obj.get("content_raw"),
            event_time=event_time,
            event_time_raw=event_time_raw,
            source_model=str(model) if model else None,
            source_model_note=(str(obj["model_note"]) if obj.get("model_note") else None),
            model_label_source="manual" if obj.get("model_note") else ("export" if model else None),
            dedup_hash=content_hash(conv.source_conversation_id, str(source_message_id))
            if source_message_id
            else content_hash(conv.source_conversation_id, str(role), text, str(ts)),
            raw_metadata=dict(obj.get("extra") or {}),
        )
