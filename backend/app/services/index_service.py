"""Qdrant 索引写入。

红线：
- Qdrant 是**可丢弃、可重建**的语义索引；权威正文永远只在 PostgreSQL。
- payload 只允许白名单里的中性元数据，**正文一个字都不许进向量库**。
- vector_id 由 message_id + chunk_index 确定性推导，重复 upsert 幂等。
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ChunkIndex, Conversation, Message
from app.services import chunking
from app.services.embedding import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger("rianvault")

NAMESPACE = uuid.UUID("2f1c4d3e-9a7b-4c5d-8e6f-000000000001")
COLLECTION_DISTANCE = "Cosine"

# payload 白名单：任何出现在下面之外的键都视为违规（测试会拦）
PAYLOAD_WHITELIST = frozenset(
    {
        "chunk_id",
        "conversation_id",
        "source_platform",
        "source_model",
        "event_time",
    }
)
MINIMAL_PAYLOAD_KEYS = frozenset({"chunk_id", "conversation_id"})
# 这些名字一旦出现在 payload 里，就是"正文漏进向量库"的信号
FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {"text", "content", "content_text", "body", "snippet", "content_raw", "title"}
)


def vector_id_for(message_id: uuid.UUID, chunk_index: int) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{message_id}:{chunk_index}")


def build_payload(
    *,
    chunk_id: uuid.UUID,
    conversation_id: uuid.UUID,
    source_platform: str | None,
    source_model: str | None,
    event_time: datetime | None,
    minimal: bool = False,
) -> dict[str, Any]:
    payload = {"chunk_id": str(chunk_id), "conversation_id": str(conversation_id)}
    if not minimal:
        if source_platform:
            payload["source_platform"] = source_platform
        if source_model:
            payload["source_model"] = source_model
        if event_time:
            payload["event_time"] = event_time.isoformat()
    _assert_payload_safe(payload)
    return payload


def _assert_payload_safe(payload: dict[str, Any]) -> None:
    keys = set(payload)
    leaking = keys & FORBIDDEN_PAYLOAD_KEYS
    if leaking:
        raise RuntimeError(f"payload 出现正文类字段，已阻止写入：{sorted(leaking)}")
    extra = keys - PAYLOAD_WHITELIST
    if extra:
        raise RuntimeError(f"payload 出现白名单外字段：{sorted(extra)}")


_client = None
_client_lock = threading.Lock()


def reset_qdrant_client() -> None:
    """测试/换配置时把单例清掉（正常运行时不需要调用）。"""
    global _client
    with _client_lock:
        if _client is not None:
            try:
                _client.close()
            except (OSError, RuntimeError) as e:
                logger.debug("关闭 Qdrant 客户端失败（忽略）：%s", e)
        _client = None


def _create_client():
    from qdrant_client import QdrantClient

    settings = get_settings()
    if settings.qdrant_mode == "local":
        try:
            return QdrantClient(path=settings.qdrant_path)
        except RuntimeError as e:
            if "already accessed" in str(e):
                raise RuntimeError(
                    f"Qdrant 存储目录被占用：{settings.qdrant_path}\n"
                    "通常是另一个 RianVault 进程（后端服务或后台建索引任务）还在跑。\n"
                    "先停掉那个进程（或等它跑完），再重试。\n"
                    "不要手删 .lock —— 那可能损坏正在写入的实例；"
                    "干净的做法是停掉占用它的进程。"
                ) from e
            raise
    return QdrantClient(url=settings.qdrant_url)


def get_qdrant():
    """获取 Qdrant 客户端（**进程内单例**）。

    为什么必须是单例（踩过的坑）：
    本地模式用 portalocker 锁住存储目录，**同一进程内开第二个客户端也会冲突**
    （实测会抛 "already accessed by another instance"）。
    后果很实际：两个并发的语义检索 → 第二个 503；后台建索引 + 前端检索 → 503。
    所以这里缓存一个客户端，全进程共用；后台索引线程与检索请求因此能共存。
    """
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            _client = _create_client()
        return _client


def ensure_collection(client, dimension: int, *, recreate: bool = False) -> str:
    from qdrant_client.http import models as qm

    name = get_settings().qdrant_collection
    exists = client.collection_exists(name)
    if exists and recreate:
        client.delete_collection(name)
        exists = False
    if not exists:
        client.create_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(size=dimension, distance=qm.Distance.COSINE),
        )
    return name


def _pending_messages(
    db: Session, *, rebuild: bool, model: str
) -> list[tuple[Message, Conversation]]:
    """待索引的消息：默认跳过已有 chunk 记录的（增量），rebuild 时全量。"""
    stmt = (
        select(Message, Conversation)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.content_text.is_not(None))
        .order_by(Message.ingested_at)
    )
    rows = list(db.execute(stmt).all())
    if rebuild:
        return rows
    indexed_msg_ids = {row[0] for row in db.execute(select(ChunkIndex.message_id)).all()}
    stale = {
        row[0]
        for row in db.execute(
            select(ChunkIndex.message_id).where(ChunkIndex.embedding_model != model)
        ).all()
    }
    todo = [pair for pair in rows if pair[0].id not in indexed_msg_ids or pair[0].id in stale]
    return todo


def _iter_chunks(
    pairs: list[tuple[Message, Conversation]], max_tokens: int
) -> Iterator[tuple[Message, Conversation, chunking.Chunk]]:
    for msg, conv in pairs:
        for chunk in chunking.chunk_message(
            str(msg.id), str(conv.id), msg.content_text or "", max_tokens=max_tokens
        ):
            yield msg, conv, chunk


def index_messages(
    db: Session,
    *,
    provider: EmbeddingProvider | None = None,
    batch_size: int = 32,
    rebuild: bool = False,
    limit_messages: int | None = None,
) -> dict:
    """把未索引的原文切片写入 Qdrant，并在 PG 登记 chunk 索引。

    返回统计 {messages, chunks, upserted, skipped_empty, model}。
    失败会把异常抛出去——不允许吞掉异常再报成功。
    """
    settings = get_settings()
    provider = provider or get_embedding_provider()
    model_name = provider.model_name

    pairs = _pending_messages(db, rebuild=rebuild, model=model_name)
    if limit_messages is not None:
        pairs = pairs[:limit_messages]

    if rebuild:
        db.query(ChunkIndex).delete()
        db.flush()

    client = get_qdrant()
    collection = ensure_collection(client, provider.dimension, recreate=rebuild)

    from qdrant_client.http import models as qm

    stats = {"messages": 0, "chunks": 0, "upserted": 0, "skipped_empty": 0, "model": model_name}
    buffer: list[tuple[Message, Conversation, chunking.Chunk]] = []

    def flush(buf: list[tuple[Message, Conversation, chunking.Chunk]]) -> None:
        if not buf:
            return
        vectors = provider.embed([c.text for _, _, c in buf])
        points = []
        for (msg, conv, chunk), vector in zip(buf, vectors, strict=True):
            vid = vector_id_for(msg.id, chunk.chunk_index)
            points.append(
                qm.PointStruct(
                    id=str(vid),
                    vector=vector,
                    payload=build_payload(
                        chunk_id=vid,
                        conversation_id=conv.id,
                        source_platform=conv.source_platform,
                        source_model=msg.source_model,
                        event_time=msg.event_time,
                        minimal=settings.qdrant_minimal_payload,
                    ),
                )
            )
            db.merge(
                ChunkIndex(
                    id=vid,
                    message_id=msg.id,
                    chunk_index=chunk.chunk_index,
                    vector_id=vid,
                    embedding_model=model_name,
                    token_estimate=chunk.token_estimate,
                )
            )
        client.upsert(collection_name=collection, points=points)
        db.commit()
        stats["upserted"] += len(points)
        # 建索引可能跑很久（CPU 上 bge-m3 每秒只能处理个位数量级的消息），
        # 定期报进度，避免看起来像卡死。只报数量，不碰正文。
        if stats["upserted"] % (batch_size * 10) < batch_size:
            logger.info("index progress: %s chunks written", stats["upserted"])

    seen_messages: set[uuid.UUID] = set()
    for item in _iter_chunks(pairs, settings.chunk_max_tokens):
        msg, _conv, _chunk = item
        if not _chunk.text.strip():
            stats["skipped_empty"] += 1
            continue
        seen_messages.add(msg.id)
        buffer.append(item)
        if len(buffer) >= batch_size:
            flush(buffer)
            buffer = []
    flush(buffer)

    stats["messages"] = len(seen_messages)
    stats["chunks"] = stats["upserted"]
    logger.info(
        "index messages=%s chunks=%s model=%s mode=%s",
        stats["messages"],
        stats["chunks"],
        model_name,
        settings.qdrant_mode,
    )
    return stats
