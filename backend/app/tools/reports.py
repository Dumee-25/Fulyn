"""Agent tools for life events, the timeline and recaps/reports."""

import datetime as dt
from typing import Any

from pydantic import Field

from app.core.time import today_local
from app.models.report import LifeEvent
from app.schemas.report import LifeEventCreate, LifeEventRead, LifeEventUpdate
from app.services import life_events, reports, timeline
from app.tools.life_logging import (
    DateRangeArgs,
    ToolArgs,
    create_tool,
    delete_tool,
    dump_records,
    update_tool,
)
from app.tools.registry import Tool, ToolContext


class SearchEventsArgs(DateRangeArgs):
    query: str | None = None
    min_importance: int | None = Field(default=None, ge=0, le=5)


def search_life_events(ctx: ToolContext, args: SearchEventsArgs) -> dict[str, Any]:
    return dump_records(LifeEventRead, life_events.list_life_events(ctx.db, **args.model_dump()))


class TimelineArgs(ToolArgs):
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    min_importance: int = Field(default=2, ge=0, le=5)
    limit: int = Field(default=40, ge=1, le=200)


def get_timeline(ctx: ToolContext, args: TimelineArgs) -> dict[str, Any]:
    items = timeline.get_timeline(ctx.db, **args.model_dump())
    return {"count": len(items), "items": [i.model_dump() for i in items]}


class DayArgs(ToolArgs):
    date: dt.date | None = Field(default=None, description="Defaults to today")


class MonthArgs(ToolArgs):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


def _report_payload(report: Any) -> dict[str, Any]:
    # The rendered report is authoritative; relay it rather than re-deriving numbers.
    return {
        "period_start": report.period_start,
        "period_end": report.period_end,
        "content": report.content,
    }


def daily_recap(ctx: ToolContext, args: DayArgs) -> dict[str, Any]:
    return _report_payload(reports.generate_daily(ctx.db, args.date or today_local(), ctx.llm))


def weekly_recap(ctx: ToolContext, args: DayArgs) -> dict[str, Any]:
    return _report_payload(reports.generate_weekly(ctx.db, args.date or today_local(), ctx.llm))


def monthly_report(ctx: ToolContext, args: MonthArgs) -> dict[str, Any]:
    return _report_payload(reports.generate_monthly(ctx.db, args.year, args.month, ctx.llm))


def report_tools() -> list[Tool]:
    return [
        create_tool(
            "create_life_event",
            "Record a notable event or outing for the timeline ('Barista with Maya', "
            "'Passed the driving test'). Not for routine things like a single coffee.",
            LifeEventCreate,
            life_events.create_life_event,
            LifeEventRead,
            LifeEvent,
        ),
        Tool(
            "search_life_events",
            "Find life events by words, importance or date range.",
            SearchEventsArgs,
            search_life_events,
        ),
        update_tool(
            "update_life_event",
            "Correct a life event.",
            LifeEventUpdate,
            "life_event_id",
            life_events.update_life_event,
            LifeEventRead,
        ),
        delete_tool(
            "delete_life_event",
            "Delete a life event.",
            "life_event_id",
            life_events.delete_life_event,
        ),
        Tool(
            "get_timeline",
            "Notable moments across events, decisions, interactions, music, important "
            "journal entries and major purchases, newest first. Good for 'what happened "
            "around the time I…' and overviews of a period.",
            TimelineArgs,
            get_timeline,
        ),
        Tool(
            "generate_daily_recap",
            "Build and save the recap of one day (mood, sleep, caffeine, money, people, "
            "highlights, music, decisions, waiting). Relay its content.",
            DayArgs,
            daily_recap,
        ),
        Tool(
            "generate_weekly_recap",
            "Build and save the recap of the week containing a date, with comparisons to "
            "the week before.",
            DayArgs,
            weekly_recap,
        ),
        Tool(
            "generate_monthly_report",
            "Build and save the life report for a month. Use for 'what was July like?'.",
            MonthArgs,
            monthly_report,
        ),
    ]
