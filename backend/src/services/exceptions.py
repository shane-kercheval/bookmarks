"""Shared exceptions for service layer operations."""


class InvalidStateError(Exception):
    """
    Raised when an operation is invalid for a resource's current state.

    Used by both bookmark and note services when operations cannot be performed
    due to the resource's state (e.g., restoring a non-deleted item, unarchiving
    a non-archived item).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
