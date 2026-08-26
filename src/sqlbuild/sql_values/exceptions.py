"""Typed SQL value errors."""


class SqlValueValidationError(ValueError):
    """An authored value cannot be represented by the typed SQL value domain."""


class SqlValueRenderingError(ValueError):
    """An adapter cannot represent a validated typed SQL value."""
