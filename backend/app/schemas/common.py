from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, ClassVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.core.time import ensure_aware

ImportanceScore = Annotated[int, Field(ge=0, le=5, description="0 disposable … 5 core memory")]
Score10 = Annotated[int, Field(ge=1, le=10)]
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
CurrencyCode = Annotated[str, Field(pattern=r"^[A-Za-z]{3}$"), AfterValidator(str.upper)]
# Naive datetimes are interpreted in the configured local timezone, never UTC.
LocalDateTime = Annotated[datetime, AfterValidator(ensure_aware)]


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlankStr = Annotated[str, AfterValidator(_not_blank)]


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PatchModel(BaseModel):
    """Base for PATCH bodies: only fields that are sent are applied.

    Fields listed in ``non_nullable`` may be omitted but not explicitly set to null.
    """

    model_config = ConfigDict(extra="forbid")
    non_nullable: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_null_required(self) -> "PatchModel":
        for name in self.model_fields_set & self.non_nullable:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)
