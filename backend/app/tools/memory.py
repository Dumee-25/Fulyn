"""Agent tools for the memory layer."""

import uuid
from datetime import date
from typing import Any

from pydantic import Field

from app.schemas.common import ImportanceScore
from app.schemas.memory import MemoryRead, MemoryType
from app.services import memories
from app.tools.life_logging import ToolArgs
from app.tools.registry import Tool, ToolContext

CONTENT_LIMIT = 1200


class SearchMemoriesArgs(ToolArgs):
    query: str | None = Field(
        default=None,
        description="What to look for, e.g. 'Sarah', 'rainy days', 'the keyboard'. "
        "Omit to list the most important memories in the range.",
    )
    date_from: date | None = Field(default=None, description="Inclusive, YYYY-MM-DD")
    date_to: date | None = Field(default=None, description="Inclusive, YYYY-MM-DD")
    min_importance: int | None = Field(default=None, ge=0, le=5)
    memory_type: MemoryType | None = None
    limit: int = Field(default=8, ge=1, le=30)


def _memory_payload(memory: Any, **extra: Any) -> dict[str, Any]:
    data = MemoryRead.model_validate(memory).model_dump(
        exclude={"created_at", "updated_at", "is_private"}
    )
    if len(data["content"]) > CONTENT_LIMIT:
        data["content"] = data["content"][:CONTENT_LIMIT] + "…"
    return {**data, **extra}


def search_memories(ctx: ToolContext, args: SearchMemoriesArgs) -> dict[str, Any]:
    # Private (vault) memories are never included here.
    filters = args.model_dump(exclude={"query", "limit"})
    if not args.query:
        found = memories.list_memories(ctx.db, limit=args.limit, **filters)
        return {"count": len(found), "results": [_memory_payload(m) for m in found]}
    response = memories.search_memories(ctx.db, args.query, limit=args.limit, **filters)
    return {
        "count": len(response.results),
        "semantic": response.semantic,
        "results": [
            _memory_payload(r, similarity=r.similarity, keyword_match=r.keyword_match)
            for r in response.results
        ],
    }


class SetMemoryImportanceArgs(ToolArgs):
    memory_id: uuid.UUID
    importance_score: ImportanceScore = Field(
        description="0 disposable, 1 mundane, 2 normal, 3 notable, 4 important, 5 core memory"
    )


def set_memory_importance(ctx: ToolContext, args: SetMemoryImportanceArgs) -> dict[str, Any]:
    memory = memories.set_memory_importance(ctx.db, args.memory_id, args.importance_score)
    return {"record": _memory_payload(memory)}


MEMORY_TOOLS = [
    Tool(
        "search_memories",
        "Search the user's memories (journal entries and other memorable records) by "
        "meaning and by words. Use for open questions about the past: people, places, "
        "'what did I do', 'memories about X'. Each result says keyword_match: whether it "
        "contains the query's words.",
        SearchMemoriesArgs,
        search_memories,
    ),
    Tool(
        "set_memory_importance",
        "Change how important a memory is. 'Remember this' or 'core memory' is 5; "
        "'that's not important' lowers it. Also updates the source journal entry.",
        SetMemoryImportanceArgs,
        set_memory_importance,
    ),
]
