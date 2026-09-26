"""Agent tools for the private vault.

Enforced in code, not just in the prompt: every vault tool refuses to run unless the
user's current message explicitly mentions the vault or private content. A turn that uses
one is marked private, so its messages are never sent to the model again as history.
"""

import re
import uuid
from datetime import date
from typing import Any

from pydantic import Field, model_validator

from app.core.errors import DomainError
from app.schemas.journal import JournalEntryRead
from app.tools.life_logging import ToolArgs, dump_record
from app.tools.registry import Tool, ToolContext
from app.vault import service as vault

EXPLICIT = re.compile(r"\b(vault|private|privately|secret|hidden)\b", re.IGNORECASE)


class VaultNotRequestedError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "the vault can only be used when the user explicitly asks for private or vault "
            "content in their message; answer from normal records instead"
        )


def _guard(ctx: ToolContext) -> None:
    if not EXPLICIT.search(ctx.user_message):
        raise VaultNotRequestedError()
    ctx.vault_accessed = True


class SearchVaultArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=8, ge=1, le=30)


def search_private_memories(ctx: ToolContext, args: SearchVaultArgs) -> dict[str, Any]:
    _guard(ctx)
    response = vault.search(ctx.db, args.query, limit=args.limit)
    return {
        "count": len(response.results),
        "results": [
            {
                "id": r.id,
                "memory_type": r.memory_type,
                "title": r.title,
                "content": r.content[:1200],
                "memory_date": r.memory_date,
                "keyword_match": r.keyword_match,
            }
            for r in response.results
        ],
    }


class ListVaultArgs(ToolArgs):
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(default=20, ge=1, le=100)


def list_vault_entries(ctx: ToolContext, args: ListVaultArgs) -> dict[str, Any]:
    _guard(ctx)
    entries = vault.list_entries(ctx.db, **args.model_dump())
    return {"count": len(entries), "entries": [dump_record(JournalEntryRead, e) for e in entries]}


class MoveArgs(ToolArgs):
    journal_entry_id: uuid.UUID | None = Field(default=None, description="Journal entry id")
    memory_id: uuid.UUID | None = Field(
        default=None, description="Or a memory id from search results"
    )

    @model_validator(mode="after")
    def _one_target(self) -> "MoveArgs":
        if (self.journal_entry_id is None) == (self.memory_id is None):
            raise ValueError("give exactly one of journal_entry_id or memory_id")
        return self


def _target(ctx: ToolContext, args: MoveArgs) -> uuid.UUID:
    if args.journal_entry_id is not None:
        return args.journal_entry_id
    return vault.journal_entry_for_memory(ctx.db, args.memory_id)


def move_to_vault(ctx: ToolContext, args: MoveArgs) -> dict[str, Any]:
    _guard(ctx)
    entry_id = _target(ctx, args)
    vault.set_entry_private(ctx.db, entry_id, True)
    return {
        "moved": str(entry_id),
        "also_private": vault.linked_counts(ctx.db, entry_id),
        "note": "the entry and everything logged with it are now only visible in the vault",
    }


def remove_from_vault(ctx: ToolContext, args: MoveArgs) -> dict[str, Any]:
    _guard(ctx)
    entry_id = _target(ctx, args)
    vault.set_entry_private(ctx.db, entry_id, False)
    return {"restored": str(entry_id)}


VAULT_TOOLS = [
    Tool(
        "search_private_memories",
        "Search the private vault. ONLY when the user explicitly asks about private or vault "
        "content (e.g. 'search my private memories about Sarah').",
        SearchVaultArgs,
        search_private_memories,
    ),
    Tool(
        "list_vault_entries",
        "List private journal entries. ONLY when the user explicitly asks for their vault.",
        ListVaultArgs,
        list_vault_entries,
    ),
    Tool(
        "move_to_vault",
        "Make a journal entry, and everything logged with it, private ('put that in the "
        "private vault').",
        MoveArgs,
        move_to_vault,
    ),
    Tool(
        "remove_from_vault",
        "Make a vault entry normal again.",
        MoveArgs,
        remove_from_vault,
    ),
]
