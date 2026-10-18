"""Snowflake adapter exceptions."""


class SnowflakeCancellationError(Exception):
    """Raised when Snowflake refuses a request to cancel a running statement."""

    code: str = "C417"

    def __init__(self, *, request_id: object, message: object) -> None:
        super().__init__(f"Snowflake refused to cancel request {request_id}: {message}")
