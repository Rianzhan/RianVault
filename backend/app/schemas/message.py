import uuid
from datetime import datetime

from pydantic import BaseModel


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    source_message_id: str | None
    parent_source_message_id: str | None
    sort_order: int
    role: str
    content_text: str | None
    content_kind: str
    event_time: datetime | None
    event_time_raw: str | None
    ingested_at: datetime
    source_model: str | None
    source_model_note: str | None
    model_label_source: str | None

    model_config = {"from_attributes": True}
