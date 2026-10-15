"""Typed SQL value errors."""


class SqlValueRenderingError(ValueError):
    """An adapter cannot represent a validated typed SQL value."""
