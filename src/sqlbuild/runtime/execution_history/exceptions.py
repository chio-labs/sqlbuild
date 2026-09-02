"""Execution history domain errors."""


class ExecutionHistoryStorageError(Exception):
    """Base error for execution history storage operations."""


class IntegrityConflictError(ExecutionHistoryStorageError):
    """Raised when an event ID is reused for different canonical content."""


class InvalidEventError(ExecutionHistoryStorageError):
    """Raised when a canonical event lacks required stable envelope content."""


class InvalidCursorError(ExecutionHistoryStorageError):
    """Raised when a storage cursor is invalid for the requested operation."""


class InvalidFilterError(ExecutionHistoryStorageError):
    """Raised when an execution history filter is contradictory or malformed."""


class InvalidLimitError(ExecutionHistoryStorageError):
    """Raised when a page limit is outside the contract bounds."""


class UnsupportedSchemaVersionError(ExecutionHistoryStorageError):
    """Raised when a backend cannot inspect or upgrade a schema version."""


class ProjectionConsistencyError(ExecutionHistoryStorageError):
    """Raised when durable facts cannot produce a consistent run projection."""
