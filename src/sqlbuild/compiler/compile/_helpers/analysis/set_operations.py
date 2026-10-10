"""Python's set-operation search over model SQL, skipped where no keyword can match."""

from __future__ import annotations

import re

_SET_OPERATION_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:UNION|INTERSECT|EXCEPT)\b", re.IGNORECASE
)
_SET_OPERATION_KEYWORDS: tuple[str, ...] = ("UNION", "INTERSECT", "EXCEPT")
_DOTTED_CAPITAL_I: str = "\u0130"


def names_set_operation(sql: str) -> bool:
    """Whether the case-insensitive search for `UNION`, `INTERSECT` or `EXCEPT` matches.

    Every character the search matches upper-cases to its keyword letter, except a dotted
    capital I, so the upper-cased text holds a keyword wherever the search can match.
    """

    folded: str = sql.upper().replace(_DOTTED_CAPITAL_I, "I")
    return any(keyword in folded for keyword in _SET_OPERATION_KEYWORDS) and (
        _SET_OPERATION_PATTERN.search(sql) is not None
    )
