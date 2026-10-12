"""Column-lineage failures."""


class UnknownLineageDialectError(ValueError):
    """Raised, as Python's parser raised `ValueError`, for a dialect Polyglot does not know."""
