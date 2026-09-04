"""Output capture runtime errors."""


class OutputCaptureInputError(ValueError):
    """Raised when output capture limits are invalid."""


class CommandOutputValidationError(ValueError):
    """Raised when a command-output record violates its wire contract."""
