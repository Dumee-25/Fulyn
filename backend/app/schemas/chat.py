import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import NonBlankStr, ReadModel


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: NonBlankStr = Field(max_length=8000)
    conversation_id: uuid.UUID | None = Field(
        default=None, description="Continue a conversation; omit to start a new one"
    )


class ChatAction(BaseModel):
    tool: str
    ok: bool
    record_id: str | None = None
    error: str | None = None


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    reply: str
    actions: list[ChatAction]


class ConversationRead(ReadModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ChatMessageRead(BaseModel):
    """User and assistant messages as shown in the UI. Tool traffic is summarized."""

    role: Literal["user", "assistant"]
    content: str
    actions: list[ChatAction] = []
    created_at: datetime
