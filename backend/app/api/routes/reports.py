import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from app.agent.llm import LLMClient, LLMUnavailableError, get_llm
from app.api.deps import DbSession, ListQuery
from app.core.time import today_local
from app.schemas.report import (
    LifeEventCreate,
    LifeEventRead,
    LifeEventUpdate,
    ReportRead,
    TimelineItem,
)
from app.services import life_events, reports, timeline

events_router = APIRouter(prefix="/events", tags=["events"])
timeline_router = APIRouter(prefix="/timeline", tags=["timeline"])
reports_router = APIRouter(prefix="/reports", tags=["reports"])


def optional_llm() -> LLMClient | None:
    """Reports still work without the model; they just have no narrative."""
    try:
        return get_llm()
    except LLMUnavailableError:
        return None


OptionalLLM = Annotated[LLMClient | None, Depends(optional_llm)]


# --- Life events -------------------------------------------------------------------


@events_router.get("", response_model=list[LifeEventRead])
def list_events(
    db: DbSession,
    params: ListQuery,
    q: Annotated[str | None, Query(max_length=200)] = None,
    min_importance: Annotated[int | None, Query(ge=0, le=5)] = None,
):
    return life_events.list_life_events(
        db, query=q, min_importance=min_importance, **params.model_dump()
    )


@events_router.post("", response_model=LifeEventRead, status_code=status.HTTP_201_CREATED)
def create_event(db: DbSession, data: LifeEventCreate):
    return life_events.create_life_event(db, data)


@events_router.get("/{event_id}", response_model=LifeEventRead)
def get_event(db: DbSession, event_id: uuid.UUID):
    return life_events.get_life_event(db, event_id)


@events_router.patch("/{event_id}", response_model=LifeEventRead)
def update_event(db: DbSession, event_id: uuid.UUID, data: LifeEventUpdate):
    return life_events.update_life_event(db, event_id, data)


@events_router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(db: DbSession, event_id: uuid.UUID) -> None:
    life_events.delete_life_event(db, event_id)


# --- Timeline ----------------------------------------------------------------------


@timeline_router.get("", response_model=list[TimelineItem])
def get_timeline(
    db: DbSession,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    min_importance: Annotated[int, Query(ge=0, le=5)] = 2,
    limit: Annotated[int, Query(ge=1, le=1000)] = 300,
):
    return timeline.get_timeline(
        db, date_from=date_from, date_to=date_to, min_importance=min_importance, limit=limit
    )


# --- Reports -----------------------------------------------------------------------


class DailyRequest(BaseModel):
    date: dt.date | None = Field(default=None, description="Defaults to today")


class WeeklyRequest(BaseModel):
    date: dt.date | None = Field(default=None, description="Any day in the week; defaults to today")


class MonthlyRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


@reports_router.get("/daily", response_model=ReportRead)
def get_daily(db: DbSession, day: Annotated[dt.date, Query(alias="date")]):
    return reports.get_daily(db, day)


@reports_router.post("/daily", response_model=ReportRead)
def generate_daily(db: DbSession, data: DailyRequest, llm: OptionalLLM):
    return reports.generate_daily(db, data.date or today_local(), llm)


@reports_router.get("/weekly", response_model=ReportRead)
def get_weekly(db: DbSession, day: Annotated[dt.date, Query(alias="date")]):
    return reports.get_weekly(db, day)


@reports_router.post("/weekly", response_model=ReportRead)
def generate_weekly(db: DbSession, data: WeeklyRequest, llm: OptionalLLM):
    return reports.generate_weekly(db, data.date or today_local(), llm)


@reports_router.get("/monthly", response_model=ReportRead)
def get_monthly(
    db: DbSession,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
):
    return reports.get_monthly(db, year, month)


@reports_router.post("/monthly", response_model=ReportRead)
def generate_monthly(db: DbSession, data: MonthlyRequest, llm: OptionalLLM):
    return reports.generate_monthly(db, data.year, data.month, llm)
