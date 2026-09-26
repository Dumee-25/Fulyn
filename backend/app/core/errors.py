"""Domain errors raised by services and translated to HTTP responses in main.py.

Messages must never contain user content (journal text, notes): they may be logged.
"""


class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    def __init__(self, resource: str) -> None:
        super().__init__(f"{resource} not found")


class InvalidReferenceError(DomainError):
    def __init__(self, field: str) -> None:
        super().__init__(f"{field} does not reference an existing record")
