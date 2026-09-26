import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import LocalDateTime, NonBlankStr, PatchModel, ReadModel

Quantity = Annotated[Decimal, Field(gt=0, max_digits=5, decimal_places=2)]
CaffeineMg = Annotated[int, Field(ge=0, le=2000)]
DrinkType = Annotated[NonBlankStr, Field(max_length=50, description="e.g. iced latte, tea")]


class CaffeineLogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consumed_at: LocalDateTime | None = Field(
        default=None, description="Defaults to now, flagged as approximate"
    )
    is_approximate: bool = False
    drink_type: DrinkType
    description: str | None = None
    # Leave null when unknown; never guess.
    estimated_caffeine_mg: CaffeineMg | None = None
    quantity: Quantity = Decimal("1")
    journal_entry_id: uuid.UUID | None = None


class CaffeineLogUpdate(PatchModel):
    non_nullable = frozenset({"consumed_at", "is_approximate", "drink_type", "quantity"})

    consumed_at: LocalDateTime | None = None
    is_approximate: bool | None = None
    drink_type: DrinkType | None = None
    description: str | None = None
    estimated_caffeine_mg: CaffeineMg | None = None
    quantity: Quantity | None = None
    journal_entry_id: uuid.UUID | None = None


class CaffeineLogRead(ReadModel):
    id: uuid.UUID
    consumed_at: datetime
    is_approximate: bool
    drink_type: str
    description: str | None
    estimated_caffeine_mg: int | None
    quantity: Decimal
    journal_entry_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
