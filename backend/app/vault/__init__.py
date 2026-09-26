"""The private vault.

Privacy is set per journal entry (``journal_entries.is_private``). Everything written in a
private entry, or linked to one, is vault content: interactions, expenses, moods, music,
decisions, events and their memories. Vault content is excluded from every normal list,
search, summary, report, timeline and dashboard, and is only readable through this package
(``app.vault.service`` and ``/api/vault``). Keeping reads here is what makes adding
encryption later a local change.
"""
