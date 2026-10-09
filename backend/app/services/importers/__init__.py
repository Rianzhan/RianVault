from app.services.importers.base import (
    CanonicalConversation,
    CanonicalMessage,
    ImporterAdapter,
)
from app.services.importers.chatgpt import ChatGPTExportAdapter
from app.services.importers.jsonl_v1 import JsonlV1Adapter

# 注册表：新增来源 = 新 adapter 文件 + 在这里加一行，不改核心模型
ADAPTERS: list[ImporterAdapter] = [ChatGPTExportAdapter(), JsonlV1Adapter()]

__all__ = [
    "ADAPTERS",
    "CanonicalConversation",
    "CanonicalMessage",
    "ChatGPTExportAdapter",
    "ImporterAdapter",
    "JsonlV1Adapter",
]
