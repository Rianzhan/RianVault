import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    body: str
    title: str | None = None
    memory_type: str = "note"
    status: str = "active"
    importance: int | None = Field(default=None, ge=1, le=5)
    event_time_start: date | None = None
    event_time_end: date | None = None
    tags: list[str] = []
    extra_metadata: dict = {}
    # actor 由 Bearer token 派生；actor_model 为客户端声明的模型标注（如 gpt-5.6-sol）
    actor_model: str | None = None
    reason: str | None = None


class MemoryUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    memory_type: str | None = None
    status: str | None = None
    importance: int | None = Field(default=None, ge=1, le=5)
    event_time_start: date | None = None
    event_time_end: date | None = None
    tags: list[str] | None = None
    extra_metadata: dict | None = None
    actor_model: str | None = None
    reason: str | None = None


class MemoryOut(BaseModel):
    id: uuid.UUID
    title: str | None
    body: str
    memory_type: str
    status: str
    importance: int | None
    event_time_start: date | None
    event_time_end: date | None
    tags: list
    extra_metadata: dict
    current_version: int
    created_by_actor: str
    created_by_model: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = {"from_attributes": True}


class SpanCreate(BaseModel):
    conversation_id: uuid.UUID
    start_message_id: uuid.UUID
    end_message_id: uuid.UUID
    span_type: str  # evidence | context
    note: str | None = None
    sort_order: int = 0
    actor_model: str | None = None
    reason: str | None = None


class SpanOut(BaseModel):
    id: uuid.UUID
    memory_id: uuid.UUID
    conversation_id: uuid.UUID
    start_message_id: uuid.UUID
    end_message_id: uuid.UUID
    span_type: str
    note: str | None
    sort_order: int
    created_at: datetime
    created_by_actor: str
    created_by_model: str | None

    model_config = {"from_attributes": True}


class ActorRequest(BaseModel):
    """restore / delete 这类不带业务字段的请求体（actor 由 token 派生）。"""

    actor_model: str | None = None
    reason: str | None = None


class RestoreRequest(ActorRequest):
    version_number: int


class VersionOut(BaseModel):
    id: uuid.UUID
    memory_id: uuid.UUID
    version_number: int
    snapshot: dict
    edited_by_actor: str
    edited_by_model: str | None
    edit_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditEventOut(BaseModel):
    id: uuid.UUID
    event_type: str
    actor: str
    actor_model: str | None
    target_type: str
    target_id: uuid.UUID
    detail: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryDetail(BaseModel):
    """Memory Detail / Genesis 视图：正文 + 来源 + 版本史 + 审计史。"""

    memory: MemoryOut
    spans: list[SpanOut]
    versions: list[VersionOut]
    audit_events: list[AuditEventOut]
