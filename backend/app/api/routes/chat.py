import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.agent import commands
from app.agent.llm import LLMClient, optional_llm
from app.api.deps import DbSession
from app.schemas.chat import ChatMessageRead, ChatRequest, ChatResponse, ConversationRead
from app.services import chat as service
from app.services import conversations

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def send_message(
    db: DbSession, data: ChatRequest, llm: Annotated[LLMClient | None, Depends(optional_llm)]
) -> ChatResponse:
    return service.handle_message(db, data.message, data.conversation_id, llm)


@router.get("/commands")
def list_commands() -> list[dict[str, str]]:
    """Slash commands, for the command picker in the chat box."""
    return [
        {
            "name": c.name,
            "usage": c.usage,
            "description": c.description,
            "kind": c.kind,
            "group": c.group,
        }
        for c in commands.COMMANDS
    ]


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(db: DbSession):
    return conversations.list_conversations(db)


@router.get("/conversations/{conversation_id}/messages", response_model=list[ChatMessageRead])
def get_messages(db: DbSession, conversation_id: uuid.UUID):
    return service.transcript(db, conversation_id)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(db: DbSession, conversation_id: uuid.UUID) -> None:
    conversations.delete_conversation(db, conversation_id)


@router.delete("/conversations", status_code=204)
def delete_all_conversations(db: DbSession) -> None:
    """Delete all chat history. Journal entries and records are kept."""
    conversations.delete_all(db)
