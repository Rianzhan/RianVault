import uuid
from datetime import datetime

from pydantic import BaseModel


class ConversationOut(BaseModel):
    id: uuid.UUID
    source_platform: str
    source_conversation_id: str | None
    title: str | None
    started_at: datetime | None
    created_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}
