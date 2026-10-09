"""ChatGPT export (conversations.json) adapter.

要点：
- mapping 是树结构：以 current_node 回溯的当前分支作为主时间线；
  parent 关系保留，整棵树的关键字段进 raw_metadata。
- 未知顶层字段不丢：进 raw_metadata + warning。
- 非 text 内容（multimodal/code/...）：原始结构进 content_raw，提不出文本则
  content_text=None + warning，绝不静默丢弃。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from app.services.importers.base import (
    CanonicalConversation,
    CanonicalMessage,
    content_hash,
)

# 已知但未单独映射的顶层字段：原样进 raw_metadata，不产生 warning
_KNOWN_CONV_KEYS = {
    "title",
    "create_time",
    "update_time",
    "id",
    "conversation_id",
    "mapping",
    "current_node",
    "moderation_results",
    "plugin_ids",
    "gizmo_id",
    "default_model_slug",
    "is_archived",
    "safe_urls",
    "blocked_urls",
    "conversation_template_id",
    "async_status",
    "voice",
    "disabled_shared_links",
}

_TEXT_CONTENT_TYPES = {"text"}


class ChatGPTExportAdapter:
    name = "chatgpt_export"
    version = "1.0.0"

    def detect(self, data: bytes, filename: str) -> bool:
        head = data[:200_000]
        if not head.lstrip().startswith(b"["):
            return False
        return b'"mapping"' in head and b'"current_node"' in head

    def parse(self, data: bytes) -> Iterator[CanonicalConversation]:
        try:
            conversations = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"conversations.json 不是合法 JSON: {e}") from e
        if not isinstance(conversations, list):
            raise TypeError("conversations.json 顶层应为数组")
        for conv in conversations:
            if isinstance(conv, dict):
                yield self._parse_conversation(conv)

    # ------------------------------------------------------------------

    def _parse_conversation(self, conv: dict[str, Any]) -> CanonicalConversation:
        warnings: list[str] = []
        conv_id = conv.get("id") or conv.get("conversation_id")

        raw_metadata: dict[str, Any] = {}
        for key, value in conv.items():
            if key in ("mapping",):
                continue
            if key not in _KNOWN_CONV_KEYS:
                warnings.append(f"未知会话字段已保留到 raw_metadata: {key}")
            raw_metadata[key] = value
        mapping = conv.get("mapping") or {}
        raw_metadata["mapping_node_count"] = len(mapping)

        if not conv_id:
            conv_dedup = content_hash("chatgpt", conv.get("title"), str(conv.get("create_time")))
            warnings.append("会话缺少 id，已用确定性哈希兜底")
        else:
            conv_dedup = None

        linear_nodes = self._linearize(mapping, conv.get("current_node"), warnings)
        default_model = conv.get("default_model_slug")

        messages: list[CanonicalMessage] = []
        for sort_order, (node_id, parent_id, msg) in enumerate(linear_nodes):
            messages.append(
                self._parse_message(
                    conv_id, node_id, parent_id, msg, sort_order, default_model, warnings
                )
            )

        return CanonicalConversation(
            source_conversation_id=str(conv_id) if conv_id else None,
            title=conv.get("title"),
            source_platform="chatgpt",
            raw_metadata=raw_metadata,
            dedup_hash=conv_dedup,
            messages=messages,
            warnings=warnings,
        )

    def _linearize(
        self,
        mapping: dict[str, Any],
        current_node: str | None,
        warnings: list[str],
    ) -> list[tuple[str, str | None, dict[str, Any] | None]]:
        """从 current_node 回溯到根，返回主时间线上的 (node_id, parent_id, message)。

        message 为 None 的节点（如根节点占位）也保留位置信息，由调用方跳过。
        """
        chain: list[str] = []
        node = current_node
        visited: set[str] = set()
        while node and node in mapping and node not in visited:
            visited.add(node)
            chain.append(node)
            parent = mapping[node].get("parent")
            node = parent if isinstance(parent, str) else None
        chain.reverse()
        if not chain:
            # current_node 缺失/损坏：退化为按 mapping 键序（尽力而为，并留 warning）
            warnings.append("current_node 缺失或损坏，主时间线退化为 mapping 键序")
            chain = list(mapping.keys())
        result: list[tuple[str, str | None, dict[str, Any] | None]] = []
        for node_id in chain:
            entry = mapping.get(node_id) or {}
            msg = entry.get("message")
            if msg is not None and not isinstance(msg, dict):
                msg = None
                warnings.append(f"节点 {node_id} 的 message 不是对象，已按占位处理")
            result.append((node_id, entry.get("parent"), msg))
        return result

    def _parse_message(
        self,
        conv_id: str | None,
        node_id: str,
        parent_id: str | None,
        msg: dict[str, Any] | None,
        sort_order: int,
        default_model: str | None,
        warnings: list[str],
    ) -> CanonicalMessage:
        if msg is None:
            # 占位节点（通常是树根）：不产生消息行，也不进隔离区——结构性跳过
            return CanonicalMessage(
                source_message_id=None,
                parent_source_message_id=parent_id,
                sort_order=sort_order,
                role="system",
                content_text=None,
                content_kind="other",
                dedup_hash=content_hash(conv_id, node_id, "__placeholder__"),
                raw_metadata={"node_id": node_id, "placeholder": True},
            )

        author = (msg.get("author") or {}).get("role") or "unknown"
        content = msg.get("content") or {}
        content_type = content.get("content_type") or "unknown"

        content_text: str | None = None
        content_kind = "text"
        if content_type in _TEXT_CONTENT_TYPES:
            parts = content.get("parts") or []
            text_parts = [p for p in parts if isinstance(p, str)]
            content_text = "\n".join(text_parts) if text_parts else None
            if len(text_parts) < len(parts):
                content_kind = "multimodal"
                warnings.append(f"消息 {msg.get('id')} 含非文本 part，原文已保留在 content_raw")
        elif content_type == "multimodal_text":
            content_kind = "multimodal"
            parts = content.get("parts") or []
            text_parts = [p for p in parts if isinstance(p, str)]
            content_text = "\n".join(text_parts) if text_parts else None
            warnings.append(f"消息 {msg.get('id')} 为 multimodal_text，文本部分已提取，原文保留")
        else:
            content_kind = "other"
            warnings.append(
                f"消息 {msg.get('id')} content_type={content_type} 未提取文本，"
                "原文保留在 content_raw"
            )

        create_time = msg.get("create_time")
        event_time = None
        event_time_raw = None
        if isinstance(create_time, (int, float)):
            event_time = datetime.fromtimestamp(create_time, tz=UTC)
            event_time_raw = repr(create_time)

        msg_meta = msg.get("metadata") or {}
        source_model = msg_meta.get("model_slug") or (
            default_model if author == "assistant" else None
        )

        source_message_id = msg.get("id")
        known_msg_keys = {
            "id",
            "author",
            "create_time",
            "update_time",
            "content",
            "status",
            "metadata",
            "end_turn",
            "weight",
            "recipient",
            "channel",
        }
        raw_metadata = {k: v for k, v in msg.items() if k not in known_msg_keys}
        raw_metadata["node_id"] = node_id

        return CanonicalMessage(
            source_message_id=str(source_message_id) if source_message_id else None,
            parent_source_message_id=parent_id,
            sort_order=sort_order,
            role=author,
            content_text=content_text,
            content_kind=content_kind,
            content_raw=content if isinstance(content, dict) else {"value": content},
            event_time=event_time,
            event_time_raw=event_time_raw,
            source_model=source_model,
            model_label_source="export" if source_model else None,
            dedup_hash=content_hash(conv_id, parent_id, author, content_text)
            if not source_message_id
            else content_hash(conv_id, str(source_message_id)),
            raw_metadata=raw_metadata,
        )
