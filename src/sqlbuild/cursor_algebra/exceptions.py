"""Cursor algebra contract errors."""

from sqlbuild.errors.contracts.exceptions import SharedInputError


class CursorAlgebraError(SharedInputError):
    """Raised when cursor values cannot form a valid typed interval."""

    code: str = "C001"
