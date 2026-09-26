"""Agent tools for cross-domain analytics. All numbers are computed by the backend."""

import datetime as dt
from typing import Any

from pydantic import Field

from app.services import analytics
from app.tools.life_logging import ToolArgs
from app.tools.registry import Tool, ToolContext


class CompareArgs(ToolArgs):
    metric: analytics.Metric = Field(
        description="spending (per day), mood, energy (1-10), sleep_minutes (night before), "
        "caffeine_drinks"
    )
    group_by: analytics.GroupBy = Field(
        description="went_out (saw someone or had an event), saw_person (needs person_name), "
        "weekend, impulse_purchase, or a median split: more_sleep, more_caffeine, "
        "better_mood, more_spending"
    )
    granularity: analytics.Granularity = Field(
        default="day", description="'week' compares weeks, e.g. weeks with more sleep"
    )
    person_name: str | None = Field(default=None, max_length=100)
    date_from: dt.date | None = Field(default=None, description="Defaults to 90 days ago")
    date_to: dt.date | None = Field(default=None, description="Defaults to today")


def compare_life(ctx: ToolContext, args: CompareArgs) -> dict[str, Any]:
    return analytics.analyze(ctx.db, **args.model_dump())


class SongsArgs(ToolArgs):
    date_from: dt.date | None = None
    date_to: dt.date | None = None


def positive_songs(ctx: ToolContext, args: SongsArgs) -> dict[str, Any]:
    return analytics.songs_in_positive_memories(ctx.db, **args.model_dump())


class DashboardArgs(ToolArgs):
    days: int = Field(default=30, ge=7, le=365, description="Trend window")


def dashboard_stats(ctx: ToolContext, args: DashboardArgs) -> dict[str, Any]:
    data = analytics.dashboard(ctx.db, days=args.days)
    # Averages and totals only; the day-by-day series are for charts.
    return {
        "today": data["today"],
        "spending": {k: v for k, v in data["spending"].items() if k != "daily"},
        "mood_average": data["mood"]["average"],
        "energy_average": data["mood"]["energy_average"],
        "sleep_average_minutes": data["sleep"]["average_minutes"],
        "people_counts": data["people"]["counts"],
        "important_memories": data["memories"]["important"],
        "decisions": data["decisions"],
        "waiting": data["waiting"],
        "window_days": args.days,
    }


def analytics_tools() -> list[Tool]:
    return [
        Tool(
            "compare_life",
            "Compare a metric between two groups of days or weeks, e.g. 'how much do I "
            "spend on days I go out?' (spending, went_out), 'how was my mood in weeks I "
            "slept more?' (mood, more_sleep, week). Report both averages, the group sizes "
            "and the caveat; if enough_data is false, say the comparison is anecdotal.",
            CompareArgs,
            compare_life,
        ),
        Tool(
            "songs_in_positive_memories",
            "Songs that appear most in positive music memories (positive emotion recorded, "
            "or a good-mood day).",
            SongsArgs,
            positive_songs,
        ),
        Tool(
            "get_dashboard_stats",
            "Current overview: month spending, subscriptions, average mood, energy and "
            "sleep over a window, people seen, important memories, decisions, waiting.",
            DashboardArgs,
            dashboard_stats,
        ),
    ]
