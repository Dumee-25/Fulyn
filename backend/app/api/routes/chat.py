import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.agent.llm import LLMClient, get_llm
from app.api.deps import DbSession
from app.schemas.chat import ChatMessageRead, ChatRequest, ChatResponse, ConversationRead
from app.services import chat as service
from app.services import conversations

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def send_message(
    db: DbSession, data: ChatRequest, llm: Annotated[LLMClient, Depends(get_llm)]
) -> ChatResponse:
    return service.handle_message(db, data.message, data.conversation_id, llm)


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(db: DbSession):
    return conversations.list_conversations(db)


@router.get("/conversations/{conversation_id}/messages", response_model=list[ChatMessageRead])
def get_messages(db: DbSession, conversation_id: uuid.UUID):
    return service.transcript(db, conversation_id)
