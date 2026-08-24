"""Microbatch state contract errors."""

from sqlbuild.errors.contracts.exceptions import ExecutorInputError


class MicrobatchStateError(ExecutorInputError):
    """Raised when persistent microbatch state cannot be addressed safely."""
