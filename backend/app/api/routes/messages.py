import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Message
from app.schemas.message import MessageOut

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("/{message_id}", response_model=MessageOut)
def get_message(message_id: uuid.UUID, db: Session = Depends(get_db)) -> MessageOut:
    msg = db.get(Message, message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="message not found")
    return MessageOut.model_validate(msg)
