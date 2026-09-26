"""Vault isolation for recaps, reports and the timeline.

Anything written in a private journal entry, or linked to one, is left out.
"""

from typing import Any

from sqlalchemy import ColumnElement, or_, select

from app.models.journal import JournalEntry


def not_private(model: Any) -> ColumnElement[bool]:
    """Filter for models with a ``journal_entry_id``: unlinked, or linked to a public entry."""
    private_entries = select(JournalEntry.id).where(JournalEntry.is_private.is_(True))
    return or_(model.journal_entry_id.is_(None), model.journal_entry_id.not_in(private_entries))
