import json
import uuid

from sqlalchemy.orm import Session

from app.agent.llm import LLMClient
from app.agent.loop import run_agent
from app.models.conversation import Conversation
from app.schemas.chat import ChatAction, ChatMessageRead, ChatResponse
from app.services import conversations, crud


def handle_message(
    db: Session, message: str, conversation_id: uuid.UUID | None, llm: LLMClient
) -> ChatResponse:
    conversation = conversations.get_or_create_conversation(db, conversation_id, message)
    result = run_agent(db, conversation, message, llm)
    return ChatResponse(
        conversation_id=conversation.id,
        reply=result.reply,
        actions=[ChatAction(**vars(action)) for action in result.actions],
    )


def transcript(db: Session, conversation_id: uuid.UUID) -> list[ChatMessageRead]:
    """User-facing view: user and assistant text, with tool results folded into actions."""
    crud.get_or_raise(db, Conversation, conversation_id)
    out: list[ChatMessageRead] = []
    pending: list[ChatAction] = []
    for message in conversations.all_messages(db, conversation_id):
        if message.role == "tool":
            pending.append(_action_from_tool_message(message.tool_name, message.content))
        elif message.role == "user":
            pending = []
            out.append(
                ChatMessageRead(role="user", content=message.content, created_at=message.created_at)
            )
        elif message.role == "assistant" and message.content.strip() and not message.tool_calls:
            out.append(
                ChatMessageRead(
                    role="assistant",
                    content=message.content,
                    actions=pending,
                    created_at=message.created_at,
                )
            )
            pending = []
    return out


def _action_from_tool_message(tool_name: str | None, content: str) -> ChatAction:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = {}
    record = payload.get("record")
    return ChatAction(
        tool=tool_name or "unknown",
        ok=bool(payload.get("ok")),
        record_id=str(record["id"]) if isinstance(record, dict) and "id" in record else None,
        error=payload.get("error"),
    )
