import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.services import analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard")
def dashboard(db: DbSession, days: Annotated[int, Query(ge=7, le=365)] = 30) -> dict[str, Any]:
    """Everything the dashboard shows, in one request. Private data is excluded."""
    return analytics.dashboard(db, days=days)


@router.get("/compare")
def compare(
    db: DbSession,
    metric: analytics.Metric,
    group_by: analytics.GroupBy,
    granularity: analytics.Granularity = "day",
    person_name: Annotated[str | None, Query(max_length=100)] = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> dict[str, Any]:
    return analytics.analyze(
        db,
        metric=metric,
        group_by=group_by,
        granularity=granularity,
        person_name=person_name,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/positive-songs")
def positive_songs(
    db: DbSession, date_from: dt.date | None = None, date_to: dt.date | None = None
) -> dict[str, Any]:
    return analytics.songs_in_positive_memories(db, date_from=date_from, date_to=date_to)
