import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CaffeineLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "caffeine_logs"
    __table_args__ = (
        CheckConstraint("estimated_caffeine_mg >= 0", name="caffeine_mg_non_negative"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    consumed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # True for "around 4" style times.
    is_approximate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    drink_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Unknown is stored as NULL, never guessed.
    estimated_caffeine_mg: Mapped[int | None] = mapped_column(Integer)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("1"), server_default=text("1")
    )
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="SET NULL"), index=True
    )
