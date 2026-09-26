"""Agent tools for subscriptions, reminders, decisions and waiting items."""

import uuid
from datetime import date
from typing import Any, Literal

from pydantic import Field

from app.core.time import now_local
from app.models.planning import Decision
from app.schemas.planning import (
    DecisionCreate,
    DecisionRead,
    DecisionStatus,
    DecisionUpdate,
    ReminderCreate,
    ReminderRead,
    ReminderStatus,
    ReminderUpdate,
    SubscriptionCreate,
    SubscriptionRead,
    SubscriptionUpdate,
    WaitingCreate,
    WaitingRead,
    WaitingStatus,
    WaitingUpdate,
)
from app.services import people, planning
from app.tools.life_logging import (
    DateRangeArgs,
    ToolArgs,
    create_tool,
    delete_tool,
    dump_record,
    update_tool,
)
from app.tools.registry import Tool, ToolContext

TIMESTAMPS = {"created_at", "updated_at"}


# --- Subscriptions -----------------------------------------------------------------


def create_subscription(ctx: ToolContext, args: SubscriptionCreate) -> dict[str, Any]:
    sub = planning.create_subscription(ctx.db, args)
    return {"record": planning.subscription_view(sub).model_dump(exclude=TIMESTAMPS)}


class GetSubscriptionsArgs(ToolArgs):
    active: bool | None = Field(default=True, description="Omit or true for active only")


def get_subscriptions(ctx: ToolContext, args: GetSubscriptionsArgs) -> dict[str, Any]:
    subs = planning.list_subscriptions(ctx.db, active=args.active)
    return {
        "count": len(subs),
        "subscriptions": [s.model_dump(exclude=TIMESTAMPS) for s in subs],
        # Exact totals: use these instead of adding amounts yourself.
        "summary": planning.summarize_subscriptions(ctx.db).model_dump(),
    }


# --- Reminders ---------------------------------------------------------------------


class GetRemindersArgs(ToolArgs):
    status: ReminderStatus | None = "pending"
    due_only: bool = Field(default=False, description="Only reminders that are due now")
    query: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


def get_reminders(ctx: ToolContext, args: GetRemindersArgs) -> dict[str, Any]:
    found = planning.list_reminders(
        ctx.db,
        status=args.status,
        due_before=now_local() if args.due_only else None,
        query=args.query,
        limit=args.limit,
    )
    return {"count": len(found), "reminders": [dump_record(ReminderRead, r) for r in found]}


class ReminderIdArgs(ToolArgs):
    reminder_id: uuid.UUID


def complete_reminder(ctx: ToolContext, args: ReminderIdArgs) -> dict[str, Any]:
    reminder = planning.complete_reminder(ctx.db, args.reminder_id)
    return {"record": dump_record(ReminderRead, reminder)}


# --- Decisions ---------------------------------------------------------------------


class SearchDecisionsArgs(DateRangeArgs):
    query: str | None = Field(default=None, description="Words in the title, decision or reason")
    status: DecisionStatus | None = None


def search_decisions(ctx: ToolContext, args: SearchDecisionsArgs) -> dict[str, Any]:
    found = planning.list_decisions(ctx.db, **args.model_dump())
    return {"count": len(found), "decisions": [dump_record(DecisionRead, d) for d in found]}


# --- Waiting items -----------------------------------------------------------------


class CreateWaitingArgs(ToolArgs):
    title: str = Field(min_length=1, max_length=200, description="e.g. 'Refund from Daraz'")
    description: str | None = None
    waiting_since: date | None = Field(default=None, description="Defaults to today")
    expected_by: date | None = None
    related_person_name: str | None = Field(
        default=None, max_length=100, description="Who it is from, if a person"
    )


def create_waiting_item(ctx: ToolContext, args: CreateWaitingArgs) -> dict[str, Any]:
    person = None
    if args.related_person_name:
        person, _ = people.resolve_person(ctx.db, args.related_person_name, create=True)
    item = planning.create_waiting(
        ctx.db,
        WaitingCreate(
            related_person_id=person.id if person else None,
            **args.model_dump(exclude={"related_person_name"}),
        ),
    )
    return {"record": planning.waiting_view(ctx.db, item).model_dump(exclude=TIMESTAMPS)}


class GetWaitingArgs(ToolArgs):
    status: WaitingStatus | None = "waiting"
    query: str | None = None


def get_waiting_items(ctx: ToolContext, args: GetWaitingArgs) -> dict[str, Any]:
    items = planning.list_waiting(ctx.db, status=args.status, query=args.query)
    return {"count": len(items), "items": [i.model_dump(exclude=TIMESTAMPS) for i in items]}


class ResolveWaitingArgs(ToolArgs):
    waiting_item_id: uuid.UUID
    status: Literal["received", "cancelled", "expired"] = "received"
    resolved_on: date | None = Field(default=None, description="Defaults to today")


def resolve_waiting_item(ctx: ToolContext, args: ResolveWaitingArgs) -> dict[str, Any]:
    item = planning.resolve_waiting(ctx.db, args.waiting_item_id, args.status, args.resolved_on)
    return {"record": planning.waiting_view(ctx.db, item).model_dump(exclude=TIMESTAMPS)}


def planning_tools() -> list[Tool]:
    return [
        Tool(
            "create_subscription",
            "Add a recurring payment (Netflix, Spotify, gym, iCloud). billing_cycle: weekly, "
            "monthly, quarterly, yearly, or custom with custom_interval_days.",
            SubscriptionCreate,
            create_subscription,
        ),
        Tool(
            "get_subscriptions",
            "List subscriptions with each one's monthly cost and next due date, plus exact "
            "monthly and yearly totals per currency.",
            GetSubscriptionsArgs,
            get_subscriptions,
        ),
        update_tool(
            "update_subscription",
            "Change a subscription (price, cycle, next billing date). Set active=false when "
            "the user cancels it.",
            SubscriptionUpdate,
            "subscription_id",
            lambda db, rid, data: planning.subscription_view(
                planning.update_subscription(db, rid, data)
            ),
            SubscriptionRead,
        ),
        delete_tool(
            "delete_subscription",
            "Delete a subscription record entirely (prefer active=false for cancellations).",
            "subscription_id",
            planning.delete_subscription,
        ),
        Tool(
            "create_reminder",
            "Create a reminder. due_at is a local datetime; use 09:00 when only a day is "
            "given. recurrence_rule: daily, weekly, monthly or yearly.",
            ReminderCreate,
            lambda ctx, args: {
                "record": dump_record(ReminderRead, planning.create_reminder(ctx.db, args))
            },
        ),
        Tool(
            "get_reminders",
            "List reminders, soonest first. Pending by default.",
            GetRemindersArgs,
            get_reminders,
        ),
        Tool(
            "complete_reminder",
            "Mark a reminder done. Recurring reminders move to their next occurrence.",
            ReminderIdArgs,
            complete_reminder,
        ),
        update_tool(
            "update_reminder",
            "Change a reminder, or cancel it with status=cancelled.",
            ReminderUpdate,
            "reminder_id",
            planning.update_reminder,
            ReminderRead,
        ),
        delete_tool(
            "delete_reminder", "Delete a reminder.", "reminder_id", planning.delete_reminder
        ),
        create_tool(
            "create_decision",
            "Record a decision the user made and their reasoning in their own words, e.g. "
            "'decided not to buy the keyboard because I already have one and it's 28k'.",
            DecisionCreate,
            planning.create_decision,
            DecisionRead,
            Decision,
        ),
        Tool(
            "search_decisions",
            "Find decisions by words, status or date. Use to answer 'why did I decide…'.",
            SearchDecisionsArgs,
            search_decisions,
        ),
        update_tool(
            "update_decision",
            "Update a decision, e.g. status reconsidered, reversed or completed.",
            DecisionUpdate,
            "decision_id",
            planning.update_decision,
            DecisionRead,
        ),
        Tool(
            "create_waiting_item",
            "Track something the user is waiting for: a refund, delivery, reply, file, "
            "results or approval.",
            CreateWaitingArgs,
            create_waiting_item,
        ),
        Tool(
            "get_waiting_items",
            "List things being waited for (status waiting by default), oldest first, with "
            "an overdue flag.",
            GetWaitingArgs,
            get_waiting_items,
        ),
        Tool(
            "resolve_waiting_item",
            "Mark a waiting item received, cancelled or expired.",
            ResolveWaitingArgs,
            resolve_waiting_item,
        ),
        update_tool(
            "update_waiting_item",
            "Change a waiting item (title, expected date, person).",
            WaitingUpdate,
            "waiting_item_id",
            lambda db, rid, data: planning.waiting_view(db, planning.update_waiting(db, rid, data)),
            WaitingRead,
        ),
    ]
