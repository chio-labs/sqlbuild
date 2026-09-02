"""Compute log storage errors."""


class ComputeLogStorageError(Exception):
    """Base error for compute log storage operations."""


class InvalidCaptureIdError(ComputeLogStorageError):
    """Raised when a capture identity is unsafe for local storage."""


class InvalidComputeLogCursorError(ComputeLogStorageError):
    """Raised when a byte cursor is malformed or beyond the stream."""


class InvalidComputeLogLimitError(ComputeLogStorageError):
    """Raised when a byte read limit is outside the public policy."""


class CaptureAlreadyExistsError(ComputeLogStorageError):
    """Raised when an invocation already has a capture."""


class CaptureNotFoundError(ComputeLogStorageError):
    """Raised when an invocation capture cannot be found."""


class CaptureStateError(ComputeLogStorageError):
    """Raised when an operation conflicts with capture disposal state."""


class ComputeLogPathError(ComputeLogStorageError):
    """Raised when a path or symlink escapes the configured root."""


class ComputeLogMetadataError(ComputeLogStorageError):
    """Raised when persisted capture metadata is invalid."""
