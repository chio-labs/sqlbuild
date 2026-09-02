"""Safe exporter health diagnostic fields."""

import re

_MAX_EXCEPTION_TYPE_LENGTH: int = 100


def sanitized_exception_type(error: BaseException) -> str:
    """Return a bounded low-cardinality exception class name."""

    sanitized: str = re.sub(r"[^A-Za-z0-9_]", "_", type(error).__name__)
    return sanitized[:_MAX_EXCEPTION_TYPE_LENGTH] or "Exception"
