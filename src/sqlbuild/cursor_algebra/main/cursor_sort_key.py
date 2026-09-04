"""Build a sortable raw cursor key."""

from datetime import datetime

from sqlbuild.cursor_algebra._helpers.comparison import as_scalar, comparison_value


def cursor_sort_key(*, raw: object, cursor_type: str) -> datetime | int:
    """Return the canonical sortable key for one raw cursor bound."""

    return comparison_value(value=as_scalar(raw=raw, cursor_type=cursor_type))
