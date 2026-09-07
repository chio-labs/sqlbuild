"""Audit execution errors."""


class AuditMeasurementExecutionError(Exception):
    """Raised when an internally validated measurement contract is unavailable."""


class AuditResultProjectionError(Exception):
    """Raised when executed audit results cannot be projected consistently."""
