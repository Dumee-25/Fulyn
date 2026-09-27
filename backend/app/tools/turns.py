"""Agent tools that act on the previous chat message: "undo that", "that was yesterday",
"remember that forever". They use exactly the records that message created."""

import datetime as dt
from typing import Any

from pydantic import Field

from app.core.errors import DomainError
from app.schemas.common import ImportanceScore
from app.services import turns
from app.tools.life_logging import ToolArgs
from app.tools.registry import Tool, ToolContext


def _conversation(ctx: ToolContext):
    if ctx.conversation_id is None:
        raise DomainError("no conversation")
    return ctx.conversation_id


class NoArgs(ToolArgs):
    pass


def undo_last_message(ctx: ToolContext, args: NoArgs) -> dict[str, Any]:
    deleted = turns.undo_last(ctx.db, _conversation(ctx))
    return {"deleted": deleted}


class MoveArgs(ToolArgs):
    date: dt.date = Field(description="The day it actually happened, YYYY-MM-DD")


def move_last_message(ctx: ToolContext, args: MoveArgs) -> dict[str, Any]:
    old, moved = turns.move_last(ctx.db, _conversation(ctx), args.date)
    return {"moved_from": old, "moved_to": args.date, "moved": moved}


class ImportanceArgs(ToolArgs):
    importance_score: ImportanceScore = Field(
        description="5 core memory / remember forever, 4 important, 1 not important"
    )


def set_last_message_importance(ctx: ToolContext, args: ImportanceArgs) -> dict[str, Any]:
    _, records = turns.last_turn(ctx.db, _conversation(ctx))
    return {"changed": turns.set_importance(ctx.db, records, args.importance_score)}


TURN_TOOLS = [
    Tool(
        "undo_last_message",
        "Delete everything the user's previous message logged ('undo that', 'scratch "
        "that', 'forget I said that').",
        NoArgs,
        undo_last_message,
    ),
    Tool(
        "move_last_message",
        "Move everything the previous message logged to another day ('that was "
        "yesterday', 'that happened on the 12th').",
        MoveArgs,
        move_last_message,
    ),
    Tool(
        "set_last_message_importance",
        "Change the importance of everything the previous message logged ('remember that "
        "forever', 'that was important', 'that's not important').",
        ImportanceArgs,
        set_last_message_importance,
    ),
]
