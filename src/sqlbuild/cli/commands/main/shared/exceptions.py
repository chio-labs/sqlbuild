"""CLI-specific expected exception types."""


class CliUserError(Exception):
    """Expected CLI-facing error that should be rendered without a traceback."""
