"""Agent tools for journal, expenses, mood, sleep and caffeine.

Tools call the same services as the REST API. The model never supplies journal
``raw_text``: create_journal_entry always stores the user's message verbatim.
"""

import uuid
from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic.json_schema import SkipJsonSchema

from app.models.caffeine import CaffeineLog
from app.models.expense import Expense
from app.models.journal import JournalEntry
from app.models.mood import MoodLog
from app.models.sleep import SleepLog
from app.schemas.caffeine import CaffeineLogCreate, CaffeineLogRead, CaffeineLogUpdate
from app.schemas.common import ImportanceScore, PatchModel, ReadModel
from app.schemas.expense import ExpenseCreate, ExpenseRead, ExpenseUpdate
from app.schemas.journal import JournalEntryCreate, JournalEntryRead, JournalEntryUpdate
from app.schemas.mood import MoodLogCreate, MoodLogRead, MoodLogUpdate
from app.schemas.sleep import SleepLogCreate, SleepLogRead, SleepLogUpdate
from app.services import caffeine, expenses, journal, moods, sleep
from app.tools.registry import Tool, ToolContext

Limit = Annotated[int, Field(ge=1, le=100, description="Maximum records to return")]
HiddenJournalId = SkipJsonSchema[uuid.UUID | None]


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DateRangeArgs(ToolArgs):
    date_from: date | None = Field(default=None, description="Inclusive start date, YYYY-MM-DD")
    date_to: date | None = Field(default=None, description="Inclusive end date, YYYY-MM-DD")
    limit: Limit = 20


def dump_record(read_model: type[ReadModel], record: Any) -> dict[str, Any]:
    return read_model.model_validate(record).model_dump(exclude={"created_at", "updated_at"})


def dump_records(read_model: type[ReadModel], records: list[Any]) -> dict[str, Any]:
    return {"count": len(records), "records": [dump_record(read_model, r) for r in records]}


def link_to_turn(ctx: ToolContext, data: BaseModel) -> None:
    """Attach this turn's journal entry when the model did not give one."""
    if getattr(data, "journal_entry_id", None) is None and ctx.journal_entry_id:
        data.journal_entry_id = ctx.journal_entry_id


def create_tool(
    name: str,
    description: str,
    create_model_cls: type[BaseModel],
    service_fn: Callable[[Any, Any], Any],
    read_model: type[ReadModel],
    orm_model: type,
) -> Tool:
    # Hide journal_entry_id from the model: linking is done by the backend.
    args_model = create_model(
        f"{name.title().replace('_', '')}Args",
        __base__=create_model_cls,
        journal_entry_id=(HiddenJournalId, None),
    )

    def handler(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
        link_to_turn(ctx, args)
        data = create_model_cls.model_validate(args.model_dump())
        record = service_fn(ctx.db, data)
        ctx.created.append((orm_model, record.id))
        return {"record": dump_record(read_model, record)}

    return Tool(name, description, args_model, handler)


def update_tool(
    name: str,
    description: str,
    update_model: type[PatchModel],
    id_field: str,
    service_fn: Callable[[Any, uuid.UUID, Any], Any],
    read_model: type[ReadModel],
) -> Tool:
    args_model = create_model(
        f"{name.title().replace('_', '')}Args",
        __base__=update_model,
        **{id_field: (uuid.UUID, Field(description="id of the record to change"))},
    )

    def handler(ctx: ToolContext, args: PatchModel) -> dict[str, Any]:
        changes = args.changes()
        record_id = changes.pop(id_field)
        if not changes:
            return {"record": None, "note": "no fields to change"}
        record = service_fn(ctx.db, record_id, update_model.model_validate(changes))
        return {"record": dump_record(read_model, record)}

    return Tool(name, description, args_model, handler)


def delete_tool(
    name: str, description: str, id_field: str, service_fn: Callable[[Any, uuid.UUID], None]
) -> Tool:
    args_model = create_model(
        f"{name.title().replace('_', '')}Args",
        __base__=ToolArgs,
        **{id_field: (uuid.UUID, Field(description="id of the record to delete"))},
    )

    def handler(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
        record_id = getattr(args, id_field)
        service_fn(ctx.db, record_id)
        return {"deleted": str(record_id)}

    return Tool(name, description, args_model, handler)


# --- Journal -----------------------------------------------------------------


class CreateJournalEntryArgs(ToolArgs):
    ai_summary: str | None = Field(
        default=None, description="Optional one-line summary. Never replaces the user's text."
    )
    mood_summary: str | None = Field(default=None, max_length=200)
    entry_date: date | None = Field(default=None, description="Defaults to today")
    importance_score: ImportanceScore = 2


def create_journal_entry(ctx: ToolContext, args: CreateJournalEntryArgs) -> dict[str, Any]:
    if ctx.journal_entry_id is not None:
        # One journal entry per message.
        existing = journal.get_journal_entry(ctx.db, ctx.journal_entry_id)
        return {"record": dump_record(JournalEntryRead, existing), "note": "already created"}
    entry = journal.create_journal_entry(
        ctx.db, JournalEntryCreate(raw_text=ctx.user_message, **args.model_dump())
    )
    ctx.journal_entry_id = entry.id
    ctx.created.append((JournalEntry, entry.id))
    return {"record": dump_record(JournalEntryRead, entry)}


class SearchJournalArgs(DateRangeArgs):
    query: str | None = Field(default=None, description="Text that must appear in the entry")
    min_importance: int | None = Field(default=None, ge=0, le=5)


def search_journal_entries(ctx: ToolContext, args: SearchJournalArgs) -> dict[str, Any]:
    # Private (vault) entries are never returned here.
    records = journal.list_journal_entries(
        ctx.db,
        query=args.query,
        min_importance=args.min_importance,
        date_from=args.date_from,
        date_to=args.date_to,
        limit=args.limit,
    )
    return dump_records(JournalEntryRead, records)


class UpdateJournalArgs(PatchModel):
    non_nullable = frozenset({"entry_date", "importance_score"})

    journal_entry_id: uuid.UUID
    ai_summary: str | None = None
    mood_summary: str | None = Field(default=None, max_length=200)
    entry_date: date | None = None
    importance_score: ImportanceScore | None = Field(
        default=None, description="0 disposable, 2 normal, 4 important, 5 core memory"
    )


def update_journal_entry(ctx: ToolContext, args: UpdateJournalArgs) -> dict[str, Any]:
    changes = args.changes()
    entry_id = changes.pop("journal_entry_id")
    entry = journal.update_journal_entry(
        ctx.db, entry_id, JournalEntryUpdate.model_validate(changes)
    )
    return {"record": dump_record(JournalEntryRead, entry)}


# --- Expenses ----------------------------------------------------------------


class GetExpensesArgs(DateRangeArgs):
    category: str | None = None
    merchant: str | None = Field(default=None, description="Partial, case-insensitive match")
    is_impulse: bool | None = None


def get_expenses(ctx: ToolContext, args: GetExpensesArgs) -> dict[str, Any]:
    return dump_records(ExpenseRead, expenses.list_expenses(ctx.db, **args.model_dump()))


class SummarizeExpensesArgs(ToolArgs):
    date_from: date | None = None
    date_to: date | None = None
    currency: str | None = Field(default=None, description="Defaults to the home currency")


def summarize_expenses(ctx: ToolContext, args: SummarizeExpensesArgs) -> dict[str, Any]:
    return {"summary": expenses.summarize_expenses(ctx.db, **args.model_dump()).model_dump()}


# --- Simple list tools -------------------------------------------------------


def list_tool(
    name: str, description: str, list_fn: Callable[..., list[Any]], read_model: type[ReadModel]
) -> Tool:
    def handler(ctx: ToolContext, args: DateRangeArgs) -> dict[str, Any]:
        return dump_records(read_model, list_fn(ctx.db, **args.model_dump()))

    return Tool(name, description, DateRangeArgs, handler)


def life_logging_tools() -> list[Tool]:
    return [
        Tool(
            "create_journal_entry",
            "Save the user's current message verbatim as a journal entry. Call once whenever "
            "the user tells you about their life. You cannot change the text.",
            CreateJournalEntryArgs,
            create_journal_entry,
        ),
        Tool(
            "search_journal_entries",
            "Find journal entries by date range, text and importance.",
            SearchJournalArgs,
            search_journal_entries,
        ),
        Tool(
            "update_journal_entry",
            "Change a journal entry's summary, date or importance. The original text "
            "cannot be changed.",
            UpdateJournalArgs,
            update_journal_entry,
        ),
        delete_tool(
            "delete_journal_entry",
            "Delete a journal entry. Only when the user explicitly asks.",
            "journal_entry_id",
            journal.delete_journal_entry,
        ),
        create_tool(
            "create_expense",
            "Record money the user spent. Amount in the home currency unless stated.",
            ExpenseCreate,
            expenses.create_expense,
            ExpenseRead,
            Expense,
        ),
        Tool(
            "get_expenses",
            "List expenses with optional filters, newest first.",
            GetExpensesArgs,
            get_expenses,
        ),
        Tool(
            "summarize_expenses",
            "Totals of spending over a date range, by category and impulse. Use this for "
            "any 'how much did I spend' question instead of adding amounts yourself.",
            SummarizeExpensesArgs,
            summarize_expenses,
        ),
        update_tool(
            "update_expense",
            "Correct an existing expense. Send only the fields that change.",
            ExpenseUpdate,
            "expense_id",
            expenses.update_expense,
            ExpenseRead,
        ),
        delete_tool("delete_expense", "Delete an expense.", "expense_id", expenses.delete_expense),
        create_tool(
            "create_mood_log",
            "Record mood (score 1-10 and/or label) and energy (1-10). Only log mood the "
            "user expressed; do not diagnose.",
            MoodLogCreate,
            moods.create_mood_log,
            MoodLogRead,
            MoodLog,
        ),
        list_tool(
            "get_mood_logs", "List mood logs, newest first.", moods.list_mood_logs, MoodLogRead
        ),
        update_tool(
            "update_mood_log",
            "Correct a mood log.",
            MoodLogUpdate,
            "mood_log_id",
            moods.update_mood_log,
            MoodLogRead,
        ),
        delete_tool("delete_mood_log", "Delete a mood log.", "mood_log_id", moods.delete_mood_log),
        create_tool(
            "create_sleep_log",
            "Record sleep. Give sleep_time/wake_time as local ISO datetimes when known, or "
            "only duration_minutes. Set is_approximate for estimates like 'around 2'.",
            SleepLogCreate,
            sleep.create_sleep_log,
            SleepLogRead,
            SleepLog,
        ),
        list_tool(
            "get_sleep_logs",
            "List sleep logs by wake-up date, newest first.",
            sleep.list_sleep_logs,
            SleepLogRead,
        ),
        update_tool(
            "update_sleep_log",
            "Correct a sleep log.",
            SleepLogUpdate,
            "sleep_log_id",
            sleep.update_sleep_log,
            SleepLogRead,
        ),
        delete_tool(
            "delete_sleep_log", "Delete a sleep log.", "sleep_log_id", sleep.delete_sleep_log
        ),
        create_tool(
            "create_caffeine_log",
            "Record a caffeinated drink. consumed_at is a local ISO datetime; omit it if "
            "no time was given. Leave estimated_caffeine_mg empty unless stated.",
            CaffeineLogCreate,
            caffeine.create_caffeine_log,
            CaffeineLogRead,
            CaffeineLog,
        ),
        list_tool(
            "get_caffeine_logs",
            "List caffeine logs, newest first.",
            caffeine.list_caffeine_logs,
            CaffeineLogRead,
        ),
        update_tool(
            "update_caffeine_log",
            "Correct a caffeine log.",
            CaffeineLogUpdate,
            "caffeine_log_id",
            caffeine.update_caffeine_log,
            CaffeineLogRead,
        ),
        delete_tool(
            "delete_caffeine_log",
            "Delete a caffeine log.",
            "caffeine_log_id",
            caffeine.delete_caffeine_log,
        ),
    ]


def finalize_turn(ctx: ToolContext) -> None:
    """Guarantee provenance for records created in this turn.

    If records were created but the model did not save a journal entry, the user's
    message is saved as one. Unlinked records are then linked to it.
    """
    records = [
        (cls, rid)
        for cls, rid in ctx.created
        if cls is not JournalEntry and hasattr(cls, "journal_entry_id")
    ]
    if not records:
        return
    if ctx.journal_entry_id is None:
        create_journal_entry(ctx, CreateJournalEntryArgs())
    for cls, record_id in records:
        record = ctx.db.get(cls, record_id)
        if record is not None and record.journal_entry_id is None:
            record.journal_entry_id = ctx.journal_entry_id
    ctx.db.commit()
