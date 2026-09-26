"""Vault isolation for recaps, reports and the timeline (see ``app.vault``)."""

from app.vault.filters import not_private

__all__ = ["not_private"]
