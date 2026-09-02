"""Exceptions raised by runtime observability contracts."""


class ObservabilityValidationError(ValueError):
    """Raised when a known observability envelope violates its contract."""
