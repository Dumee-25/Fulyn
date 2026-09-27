"""The agent loop.

user message -> model (with tools) -> validated tool calls -> results back to the model
-> ... -> final reply. Bounded by AGENT_MAX_TOOL_ITERATIONS.
"""

import logging
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from app.agent.llm import LLMClient
from app.agent.prompt import build_system_prompt
from app.core.config import get_settings
from app.core.time import now_local
from app.models.conversation import Conversation
from app.services import conversations, turns
from app.tools.catalog import build_registry
from app.tools.life_logging import finalize_turn
from app.tools.registry import ToolContext, ToolRegistry

logger = logging.getLogger(__name__)

STEP_LIMIT_REPLY = (
    "I had to stop before finishing because this took too many steps. "
    "Some things may have been saved; check the pages or ask me what I logged."
)


@dataclass
class ActionRecord:
    tool: str
    ok: bool
    record_id: str | None = None
    error: str | None = None


@dataclass
class AgentResult:
    reply: str
    actions: list[ActionRecord] = field(default_factory=list)
    # Records this turn created, the ids of its chat messages, and its journal entry.
    created: list[tuple[type, uuid.UUID]] = field(default_factory=list)
    message_ids: list[uuid.UUID] = field(default_factory=list)
    journal_entry_id: uuid.UUID | None = None


@lru_cache
def default_registry() -> ToolRegistry:
    return build_registry()


READ_ONLY_PREFIXES = ("get_", "search_", "find_", "summarize_", "compare_", "songs_")


@lru_cache
def read_only_registry() -> ToolRegistry:
    """Tools that only read, for messages that must not log anything (/nolog)."""
    full = build_registry()
    registry = ToolRegistry()
    for name in full.names():
        if name.startswith(READ_ONLY_PREFIXES) and not name.startswith("search_private"):
            registry.register(full.get(name))
    return registry


def run_agent(
    db: Session,
    conversation: Conversation,
    user_message: str,
    llm: LLMClient,
    registry: ToolRegistry | None = None,
    stored_message: str | None = None,
) -> AgentResult:
    """``user_message`` goes to the model; ``stored_message`` (default: the same) is what the
    transcript shows, e.g. with a trailing /core that the model shouldn't see."""
    settings = get_settings()
    registry = registry or default_registry()
    tools = registry.schemas()

    history = conversations.recent_history(db, conversation.id, settings.agent_history_messages)
    user_record = conversations.add_message(
        db, conversation, "user", stored_message or user_message
    )
    turn = [user_record.id]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt(now_local())},
        *history,
        {"role": "user", "content": user_message},
    ]

    ctx = ToolContext(db=db, user_message=user_message, llm=llm, conversation_id=conversation.id)
    actions: list[ActionRecord] = []
    reply = STEP_LIMIT_REPLY

    for _ in range(settings.agent_max_tool_iterations):
        response = llm.chat(messages, tools)
        raw_calls = [
            call.raw or {"function": {"name": call.name, "arguments": call.arguments}}
            for call in response.tool_calls
        ]
        assistant: dict[str, Any] = {"role": "assistant", "content": response.content}
        if raw_calls:
            assistant["tool_calls"] = raw_calls
        messages.append(assistant)
        turn.append(
            conversations.add_message(
                db, conversation, "assistant", response.content, tool_calls=raw_calls or None
            ).id
        )

        if not response.tool_calls:
            reply = response.content.strip() or "Done."
            break

        for call in response.tool_calls:
            result = registry.execute(ctx, call.name, call.arguments)
            record = result.payload.get("record")
            actions.append(
                ActionRecord(
                    tool=call.name,
                    ok=result.ok,
                    record_id=str(record["id"]) if isinstance(record, dict) else None,
                    error=None if result.ok else result.payload.get("error"),
                )
            )
            content = result.to_message_content()
            messages.append({"role": "tool", "content": content, "tool_name": call.name})
            turn.append(
                conversations.add_message(db, conversation, "tool", content, tool_name=call.name).id
            )
    else:
        logger.warning("Agent hit the tool iteration limit")
        turn.append(conversations.add_message(db, conversation, "assistant", reply).id)

    finalize_turn(ctx)
    turns.record_turn(db, conversation.id, user_record.id, ctx.created)
    if ctx.vault_accessed:
        conversations.mark_private(db, turn)
    db.commit()
    return AgentResult(
        reply=reply,
        actions=actions,
        created=list(ctx.created),
        message_ids=turn,
        journal_entry_id=ctx.journal_entry_id,
    )
