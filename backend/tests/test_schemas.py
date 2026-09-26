"""Validation rules that do not need a database."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.schemas.caffeine import CaffeineLogCreate
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.schemas.journal import JournalEntryCreate, JournalEntryUpdate
from app.schemas.mood import MoodLogCreate
from app.schemas.sleep import SleepLogCreate

COLOMBO = ZoneInfo("Asia/Colombo")


class TestMoney:
    def test_string_amount_keeps_exact_decimal(self) -> None:
        assert ExpenseCreate(amount="1450.50").amount == Decimal("1450.50")

    def test_rejects_sub_cent_precision(self) -> None:
        with pytest.raises(ValidationError):
            ExpenseCreate(amount="850.555")

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            ExpenseCreate(amount="-1")

    def test_amount_is_decimal_not_float(self) -> None:
        assert isinstance(ExpenseCreate(amount=850).amount, Decimal)


class TestExpenseFields:
    def test_category_matched_case_insensitively(self) -> None:
        assert ExpenseCreate(amount=1, category="  cafe ").category == "Cafe"

    def test_unknown_category_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExpenseCreate(amount=1, category="Crypto")

    def test_currency_uppercased(self) -> None:
        assert ExpenseCreate(amount=1, currency="usd").currency == "USD"

    def test_patch_cannot_null_required_field(self) -> None:
        with pytest.raises(ValidationError):
            ExpenseUpdate(amount=None)

    def test_patch_tracks_only_sent_fields(self) -> None:
        assert ExpenseUpdate(amount="850").changes() == {"amount": Decimal("850")}

    def test_unknown_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExpenseCreate(amount=1, amout=2)


class TestJournal:
    def test_raw_text_preserved_verbatim(self) -> None:
        text = "  Slept like shit.\nPretty good day overall.  "
        assert JournalEntryCreate(raw_text=text).raw_text == text

    def test_blank_text_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JournalEntryCreate(raw_text="   ")

    @pytest.mark.parametrize("score", [0, 5])
    def test_importance_bounds_accepted(self, score: int) -> None:
        assert JournalEntryCreate(raw_text="x", importance_score=score).importance_score == score

    @pytest.mark.parametrize("score", [-1, 6])
    def test_importance_out_of_range(self, score: int) -> None:
        with pytest.raises(ValidationError):
            JournalEntryUpdate(importance_score=score)


class TestMood:
    def test_requires_some_signal(self) -> None:
        with pytest.raises(ValidationError):
            MoodLogCreate(notes="meh")

    def test_label_normalized(self) -> None:
        assert MoodLogCreate(label=" Good ").label == "good"

    def test_score_range(self) -> None:
        with pytest.raises(ValidationError):
            MoodLogCreate(score=11)


class TestSleepAndCaffeine:
    def test_duration_only_is_valid(self) -> None:
        log = SleepLogCreate(duration_minutes=300, is_approximate=True)
        assert log.sleep_time is None and log.wake_time is None

    def test_wake_must_follow_sleep(self) -> None:
        with pytest.raises(ValidationError):
            SleepLogCreate(sleep_time="2026-09-26T07:00", wake_time="2026-09-26T02:00")

    def test_naive_datetime_is_local_not_utc(self) -> None:
        log = CaffeineLogCreate(drink_type="iced latte", consumed_at="2026-09-26T16:00:00")
        assert log.consumed_at == datetime(2026, 9, 26, 16, tzinfo=COLOMBO)

    def test_caffeine_mg_optional(self) -> None:
        assert CaffeineLogCreate(drink_type="tea").estimated_caffeine_mg is None
