import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation import ChatMessage, Conversation
from app.services import crud


def get_or_create_conversation(
    db: Session, conversation_id: uuid.UUID | None, first_message: str
) -> Conversation:
    if conversation_id is not None:
        return crud.get_or_raise(db, Conversation, conversation_id)
    conversation = Conversation(title=first_message.strip()[:80] or None)
    db.add(conversation)
    db.commit()
    return conversation


def list_conversations(db: Session, limit: int = 50) -> list[Conversation]:
    stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def add_message(
    db: Session,
    conversation: Conversation,
    role: str,
    content: str = "",
    *,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_name: str | None = None,
) -> ChatMessage:
    message = ChatMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_name=tool_name,
    )
    db.add(message)
    conversation.updated_at = func.now()
    # Commit each message on its own so a failing tool (which rolls back) cannot
    # discard the transcript.
    db.commit()
    return message


def all_messages(db: Session, conversation_id: uuid.UUID) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
    )
    return list(db.scalars(stmt))


def recent_history(db: Session, conversation_id: uuid.UUID, limit: int) -> list[dict[str, Any]]:
    """The last ``limit`` messages in Ollama chat format, starting at a user message."""
    if limit == 0:
        return []
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(reversed(list(db.scalars(stmt))))
    # Never start mid-turn with an orphaned tool result.
    while messages and messages[0].role != "user":
        messages.pop(0)
    return [to_llm_message(m) for m in messages]


def to_llm_message(message: ChatMessage) -> dict[str, Any]:
    out: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        out["tool_calls"] = message.tool_calls
    if message.tool_name:
        out["tool_name"] = message.tool_name
    return out
