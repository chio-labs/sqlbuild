"""SQL test execution exceptions."""


class SqlTestRenderingError(RuntimeError):
    """Raised when native SQL-test rendering returns an invalid response."""
