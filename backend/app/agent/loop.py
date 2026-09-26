"""The agent loop.

user message -> model (with tools) -> validated tool calls -> results back to the model
-> ... -> final reply. Bounded by AGENT_MAX_TOOL_ITERATIONS.
"""

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from app.agent.llm import LLMClient
from app.agent.prompt import build_system_prompt
from app.core.config import get_settings
from app.core.time import now_local
from app.models.conversation import Conversation
from app.services import conversations
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


@lru_cache
def default_registry() -> ToolRegistry:
    return build_registry()


def run_agent(
    db: Session,
    conversation: Conversation,
    user_message: str,
    llm: LLMClient,
    registry: ToolRegistry | None = None,
) -> AgentResult:
    settings = get_settings()
    registry = registry or default_registry()
    tools = registry.schemas()

    history = conversations.recent_history(db, conversation.id, settings.agent_history_messages)
    conversations.add_message(db, conversation, "user", user_message)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt(now_local())},
        *history,
        {"role": "user", "content": user_message},
    ]

    ctx = ToolContext(db=db, user_message=user_message, llm=llm)
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
        conversations.add_message(
            db, conversation, "assistant", response.content, tool_calls=raw_calls or None
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
            conversations.add_message(db, conversation, "tool", content, tool_name=call.name)
    else:
        logger.warning("Agent hit the tool iteration limit")
        conversations.add_message(db, conversation, "assistant", reply)

    finalize_turn(ctx)
    db.commit()
    return AgentResult(reply=reply, actions=actions)
