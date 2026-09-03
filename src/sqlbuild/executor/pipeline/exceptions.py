"""Execution pipeline errors."""


class AuditConcurrencyError(RuntimeError):
    """Raised when standalone audit concurrency is invalid."""


class AuditOutcomeError(RuntimeError):
    """Raised when audit execution returns an unknown quality outcome."""
