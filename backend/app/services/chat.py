import json
import uuid

from sqlalchemy.orm import Session

from app.agent import commands
from app.agent.llm import LLMClient, LLMUnavailableError
from app.agent.loop import read_only_registry, run_agent
from app.models.conversation import Conversation
from app.schemas.chat import ChatAction, ChatMessageRead, ChatResponse
from app.services import conversations, crud


def handle_message(
    db: Session, message: str, conversation_id: uuid.UUID | None, llm: LLMClient | None
) -> ChatResponse:
    conversation = conversations.get_or_create_conversation(db, conversation_id, message)
    parsed = commands.parse(message)

    # Slash commands and modifiers on their own: handled here, without the model.
    if parsed.command or not parsed.text:
        user = conversations.add_message(db, conversation, "user", message)
        ctx = commands.Context(db, conversation.id, user.id, llm)
        result = (
            commands.run(ctx, parsed)
            if parsed.command
            else commands.apply_standalone_modifiers(ctx, parsed.modifiers)
        )
        reply = conversations.add_message(db, conversation, "assistant", result.reply)
        if result.private:
            conversations.mark_private(db, [user.id, reply.id])
        return _response(conversation.id, result.reply, result.actions)

    if llm is None:
        raise LLMUnavailableError(
            "The language model isn't available (check that Ollama is running and OLLAMA_MODEL "
            "is set in .env), so only /commands work right now."
        )
    registry = read_only_registry() if "nolog" in parsed.modifiers else None
    agent = run_agent(db, conversation, parsed.text, llm, registry=registry, stored_message=message)
    reply, actions = agent.reply, list(agent.actions)

    # Modifiers inside a normal message apply to what this message logged.
    records = [r for cls, rid in agent.created if (r := db.get(cls, rid)) is not None]
    ctx = commands.Context(db, conversation.id, agent.message_ids[0], llm)
    notes = []
    for name, score in commands.IMPORTANCE_MODIFIERS.items():
        if name in parsed.modifiers:
            if records:
                notes.append(commands.apply_importance(ctx, score, records))
            else:
                notes.append(
                    commands.CommandResult(
                        f"(Nothing was logged, so /{name} had nothing to apply to.)"
                    )
                )
    if "private" in parsed.modifiers:
        if records:
            notes.append(commands.apply_private(ctx, records))
            conversations.mark_private(db, agent.message_ids)
        else:
            notes.append(
                commands.CommandResult("(Nothing was logged, so /private had nothing to move.)")
            )
    for note in notes:
        reply += "\n\n" + note.reply
        actions += note.actions
    if notes:
        # Keep the stored reply in step with what the user sees.
        conversations.append_to_last_assistant(db, conversation.id, reply)
    return _response(conversation.id, reply, actions)


def _response(conversation_id: uuid.UUID, reply: str, actions: list) -> ChatResponse:
    return ChatResponse(
        conversation_id=conversation_id,
        reply=reply,
        actions=[ChatAction(**vars(action)) for action in actions],
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
