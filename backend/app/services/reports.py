"""Generate and store daily recaps, weekly recaps and monthly reports.

Generated on demand; regenerating a period replaces its stored report. Numbers come from
``app.reports.stats``; the model only adds optional prose (``app.reports.narrative``).
"""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.llm import LLMClient
from app.core.errors import DomainError, NotFoundError
from app.core.time import today_local
from app.models.report import DailyRecap, MonthlyReport, WeeklyRecap
from app.reports import narrative, render, stats
from app.schemas.report import ReportRead

EMPTY = "Nothing was logged for this period."


class FuturePeriodError(DomainError):
    def __init__(self) -> None:
        super().__init__("that period has not started yet")


def week_start_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def month_end(year: int, month: int) -> date:
    return date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)


def _check_started(start: date) -> None:
    if start > today_local():
        raise FuturePeriodError()


# --- Daily -------------------------------------------------------------------------


def _daily_read(r: DailyRecap) -> ReportRead:
    return ReportRead(
        kind="daily",
        period_start=r.date,
        period_end=r.date,
        content=r.content,
        data=r.data,
        generated_at=r.generated_at,
    )


def generate_daily(db: Session, day: date, llm: LLMClient | None) -> ReportRead:
    _check_started(day)
    data = stats.daily(db, day)
    if stats.is_empty(data):
        content = f"# {day:%A, %d %B %Y}\n\n{EMPTY}\n"
    else:
        prose = narrative.daily_narrative(llm, data)
        # Kept alongside the numbers so the timeline can show it as the day's summary.
        data["narrative"] = prose
        content = render.render_daily(data, prose)
    recap = db.scalar(select(DailyRecap).where(DailyRecap.date == day)) or DailyRecap(date=day)
    recap.content, recap.data, recap.generated_at = content, data, func.now()
    db.add(recap)
    db.commit()
    db.refresh(recap)
    return _daily_read(recap)


def get_daily(db: Session, day: date) -> ReportRead:
    recap = db.scalar(select(DailyRecap).where(DailyRecap.date == day))
    if recap is None:
        raise NotFoundError("Daily recap")
    return _daily_read(recap)


# --- Weekly ------------------------------------------------------------------------


def _weekly_read(r: WeeklyRecap) -> ReportRead:
    return ReportRead(
        kind="weekly",
        period_start=r.week_start,
        period_end=r.week_start + timedelta(days=6),
        content=r.content,
        data=r.data,
        generated_at=r.generated_at,
    )


def generate_weekly(db: Session, day_in_week: date, llm: LLMClient | None) -> ReportRead:
    start = week_start_of(day_in_week)
    _check_started(start)
    data = stats.weekly(db, start)
    if stats.is_empty(data):
        content = f"# Week of {start:%d %B %Y}\n\n{EMPTY}\n"
    else:
        content = render.render_weekly(data, narrative.weekly_narrative(llm, data))
    recap = db.scalar(select(WeeklyRecap).where(WeeklyRecap.week_start == start)) or WeeklyRecap(
        week_start=start
    )
    recap.content, recap.data, recap.generated_at = content, data, func.now()
    db.add(recap)
    db.commit()
    db.refresh(recap)
    return _weekly_read(recap)


def get_weekly(db: Session, day_in_week: date) -> ReportRead:
    recap = db.scalar(
        select(WeeklyRecap).where(WeeklyRecap.week_start == week_start_of(day_in_week))
    )
    if recap is None:
        raise NotFoundError("Weekly recap")
    return _weekly_read(recap)


# --- Monthly -----------------------------------------------------------------------


def _monthly_read(r: MonthlyReport) -> ReportRead:
    return ReportRead(
        kind="monthly",
        period_start=date(r.year, r.month, 1),
        period_end=month_end(r.year, r.month),
        content=r.content,
        data=r.data,
        generated_at=r.generated_at,
    )


def generate_monthly(db: Session, year: int, month: int, llm: LLMClient | None) -> ReportRead:
    start = date(year, month, 1)
    _check_started(start)
    data = stats.monthly(db, year, month)
    name = start.strftime("%B %Y")
    if stats.is_empty(data):
        content = f"# {name}\n\n{EMPTY}\n"
    else:
        excerpts = stats.journal_excerpts(db, start, month_end(year, month))
        sentence, themes = narrative.monthly_narrative(llm, data, excerpts)
        data["month_in_one_sentence"] = sentence
        data["themes"] = themes
        content = render.render_monthly(data, sentence, themes, name)
    report = db.scalar(
        select(MonthlyReport).where(MonthlyReport.year == year, MonthlyReport.month == month)
    ) or MonthlyReport(year=year, month=month)
    report.content, report.data, report.generated_at = content, data, func.now()
    db.add(report)
    db.commit()
    db.refresh(report)
    return _monthly_read(report)


def get_monthly(db: Session, year: int, month: int) -> ReportRead:
    report = db.scalar(
        select(MonthlyReport).where(MonthlyReport.year == year, MonthlyReport.month == month)
    )
    if report is None:
        raise NotFoundError("Monthly report")
    return _monthly_read(report)
