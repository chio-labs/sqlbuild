"""Release gate failures."""


class ReleaseGateError(RuntimeError):
    """Raised when a workflow or expression cannot be read as the gate check expects."""
