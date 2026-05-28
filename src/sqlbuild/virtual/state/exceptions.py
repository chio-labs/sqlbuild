"""Virtual state store exceptions."""

from __future__ import annotations


class StateBackendError(RuntimeError):
    """Raised when state backend operations fail."""


class StateBackendConfigError(StateBackendError):
    """Raised when state backend configuration is invalid."""


class StateSchemaInvalidError(StateBackendError):
    """Raised when an operation requires a valid state schema."""


class StateBackupNotFoundError(StateBackendError):
    """Raised when rollback cannot find a state backup."""
