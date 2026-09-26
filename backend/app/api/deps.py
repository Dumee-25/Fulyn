from datetime import date
from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.crud import MAX_LIMIT

DbSession = Annotated[Session, Depends(get_db)]


class ListParams(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    limit: int = 100
    offset: int = 0


def list_params(
    date_from: Annotated[date | None, Query(description="Inclusive, local date")] = None,
    date_to: Annotated[date | None, Query(description="Inclusive, local date")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ListParams:
    return ListParams(date_from=date_from, date_to=date_to, limit=limit, offset=offset)


ListQuery = Annotated[ListParams, Depends(list_params)]
