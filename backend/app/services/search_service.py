"""检索：关键词（PostgreSQL）+ 语义（Qdrant）+ 混合。

红线：
- 正文永远从 PostgreSQL 取，Qdrant 只负责给出"哪些 chunk 相近"。
- 日志只记命中数量，**绝不记录 query 文本**（私人内容不出日志）。
- 检索只读，不产生版本/审计事件（写入才需要）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ChunkIndex, Conversation, Message
from app.services.embedding import EmbeddingProvider, get_embedding_provider
from app.services.index_service import get_qdrant

logger = logging.getLogger("rianvault")

KEYWORD_ONLY_SCORE = 0.3


@dataclass
class SearchHit:
    message_id: str
    conversation_id: str
    conversation_title: str | None
    source_platform: str | None
    source_model: str | None
    role: str
    content_text: str
    event_time: str | None
    score: float
    match_types: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "conversation_title": self.conversation_title,
            "source_platform": self.source_platform,
            "source_model": self.source_model,
            "role": self.role,
            "content_text": self.content_text,
            "event_time": self.event_time,
            "score": round(self.score, 4),
            "match_types": self.match_types,
        }


@dataclass
class Filters:
    source_platform: str | None = None
    conversation_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    role: str | None = None
    source_model: str | None = None


def _apply_filters(stmt: Select, filters: Filters) -> Select:
    if filters.source_platform:
        stmt = stmt.where(Conversation.source_platform == filters.source_platform)
    if filters.conversation_id:
        stmt = stmt.where(Message.conversation_id == filters.conversation_id)
    if filters.role:
        stmt = stmt.where(Message.role == filters.role)
    if filters.source_model:
        stmt = stmt.where(Message.source_model == filters.source_model)
    if filters.date_from:
        stmt = stmt.where(
            Message.event_time >= datetime.combine(filters.date_from, datetime.min.time())
        )
    if filters.date_to:
        stmt = stmt.where(
            Message.event_time <= datetime.combine(filters.date_to, datetime.max.time())
        )
    return stmt


def keyword_search(
    db: Session, query: str, *, limit: int = 20, filters: Filters | None = None
) -> list[SearchHit]:
    """纯 PostgreSQL 子串检索（多词按 AND）。没有向量库也能用。"""
    filters = filters or Filters()
    terms = [t for t in query.replace("\u3000", " ").split() if t] or [query]
    stmt = select(Message, Conversation).join(
        Conversation, Conversation.id == Message.conversation_id
    )
    for term in terms:
        pattern = f"%{_escape_like(term)}%"
        stmt = stmt.where(Message.content_text.ilike(pattern))
    stmt = _apply_filters(stmt, filters).order_by(Message.event_time.desc()).limit(limit)

    hits = []
    for msg, conv in db.execute(stmt).all():
        hits.append(
            SearchHit(
                message_id=str(msg.id),
                conversation_id=str(conv.id),
                conversation_title=conv.title,
                source_platform=conv.source_platform,
                source_model=msg.source_model,
                role=msg.role,
                content_text=msg.content_text or "",
                event_time=msg.event_time.isoformat() if msg.event_time else None,
                score=KEYWORD_ONLY_SCORE,
                match_types=["keyword"],
            )
        )
    return hits


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def semantic_search(
    db: Session,
    query: str,
    *,
    limit: int = 20,
    filters: Filters | None = None,
    provider: EmbeddingProvider | None = None,
) -> list[SearchHit]:
    """向量检索：Qdrant 给候选 chunk，正文一律回查 PostgreSQL。"""
    filters = filters or Filters()
    provider = provider or get_embedding_provider()
    vector = provider.embed([query])[0]
    client = get_qdrant()
    collection = get_settings().qdrant_collection
    if not client.collection_exists(collection):
        return []

    # 先多取一些，过滤后仍可能不足 limit
    response = client.query_points(
        collection_name=collection,
        query=vector,
        limit=max(limit * 4, 20),
        with_payload=True,
    )
    results = list(response.points)

    scores: dict[str, float] = {}
    vector_ids: list[str] = []
    for hit in results:
        chunk_id = (hit.payload or {}).get("chunk_id")
        if not chunk_id:
            continue
        vector_ids.append(chunk_id)
        scores[chunk_id] = max(scores.get(chunk_id, 0.0), float(hit.score))

    if not vector_ids:
        return []

    # 过滤一律回查 PG（payload 里只有中性元数据，不参与过滤判断）
    rows = db.execute(
        _apply_filters(
            select(ChunkIndex, Message, Conversation)
            .join(Message, Message.id == ChunkIndex.message_id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                ChunkIndex.vector_id.in_(
                    [v for v in (_as_uuid(x) for x in vector_ids) if v is not None]
                )
            ),
            filters,
        )
    ).all()

    hits: dict[str, SearchHit] = {}
    for chunk, msg, conv in rows:
        score = scores.get(str(chunk.vector_id), 0.0)
        existing = hits.get(str(msg.id))
        if existing is None or score > existing.score:
            hits[str(msg.id)] = SearchHit(
                message_id=str(msg.id),
                conversation_id=str(conv.id),
                conversation_title=conv.title,
                source_platform=conv.source_platform,
                source_model=msg.source_model,
                role=msg.role,
                content_text=msg.content_text or "",
                event_time=msg.event_time.isoformat() if msg.event_time else None,
                score=score,
                match_types=["semantic"],
            )

    ordered = sorted(hits.values(), key=lambda h: h.score, reverse=True)[:limit]
    return ordered


def _as_uuid(value: str):
    import uuid

    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


def hybrid_search(
    db: Session,
    query: str,
    *,
    limit: int = 20,
    filters: Filters | None = None,
    provider: EmbeddingProvider | None = None,
) -> list[SearchHit]:
    """语义结果为主，关键词补充；语义分低的关键词命中排在后面。"""
    semantic = semantic_search(db, query, limit=limit, filters=filters, provider=provider)
    try:
        keyword = keyword_search(db, query, limit=limit, filters=filters)
    except SQLAlchemyError as e:  # 关键词检索失败不应拖垮语义结果
        logger.warning("keyword search failed: %s", type(e).__name__)
        keyword = []

    merged: dict[str, SearchHit] = {h.message_id: h for h in semantic}
    for hit in keyword:
        if hit.message_id in merged:
            merged[hit.message_id].match_types = ["semantic", "keyword"]
        else:
            merged[hit.message_id] = hit
    return sorted(merged.values(), key=lambda h: h.score, reverse=True)[:limit]


def search(
    db: Session,
    query: str,
    *,
    mode: str = "hybrid",
    limit: int = 20,
    filters: Filters | None = None,
    provider: EmbeddingProvider | None = None,
) -> list[SearchHit]:
    if not query or not query.strip():
        return []
    if mode == "keyword":
        hits = keyword_search(db, query, limit=limit, filters=filters)
    elif mode == "semantic":
        hits = semantic_search(db, query, limit=limit, filters=filters, provider=provider)
    elif mode == "hybrid":
        hits = hybrid_search(db, query, limit=limit, filters=filters, provider=provider)
    else:
        raise ValueError(f"未知检索模式: {mode}（可用：keyword|semantic|hybrid）")
    # 只记数量，绝不记 query 文本
    logger.info("search mode=%s hits=%s", mode, len(hits))
    return hits


def has_indexed_chunks(db: Session) -> bool:
    return db.scalar(select(ChunkIndex.id).limit(1)) is not None
