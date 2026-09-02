"""Storage page limit validation entrypoint."""

from sqlbuild.runtime.execution_history._helpers.validation import (
    validate_page_limit as _validate_page_limit,
)


def validate_page_limit(limit: int) -> None:
    """Validate a positive page limit no greater than the public maximum."""

    _validate_page_limit(limit)
