import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Numeric, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Expense(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "expenses"
    __table_args__ = (CheckConstraint("amount >= 0", name="amount_non_negative"),)

    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Free text so categories can be customised later; the API validates the default set.
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    merchant: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_impulse: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    impulse_reason: Mapped[str | None] = mapped_column(Text)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="SET NULL"), index=True
    )
