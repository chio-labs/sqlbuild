"""Recognition for the first-class empty relation fixture marker."""

from __future__ import annotations

import re

_EMPTY_FIXTURE_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*SELECT\s+\*\s+FROM\s+__empty_fixture\s*\(\s*\)\s*$",
    re.IGNORECASE,
)


def is_empty_fixture_query(sql: str) -> bool:
    """Return whether SQL is exactly the empty relation fixture marker."""

    return _EMPTY_FIXTURE_PATTERN.fullmatch(sql) is not None
