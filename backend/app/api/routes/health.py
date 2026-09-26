from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.version import __version__
from app.db.session import get_db
from app.schemas.health import HealthResponse
from app.services.health import database_is_up

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    db_ok = database_is_up(db)
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        app=settings.app_name,
        version=__version__,
        environment=settings.app_env,
        database="ok" if db_ok else "unavailable",
        timezone=settings.default_timezone,
        currency=settings.default_currency,
    )


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """Process is up; does not touch the database."""
    return {"status": "ok"}
