"""Python's set-operation search over model SQL, tried only where a keyword can match."""

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
    capital I, so the upper-cased text holds a keyword wherever the search can match. When
    upper-casing keeps every character in place, the search is tried only at those offsets.
    """

    folded: str = sql.upper().replace(_DOTTED_CAPITAL_I, "I")
    if len(folded) != len(sql):
        return any(keyword in folded for keyword in _SET_OPERATION_KEYWORDS) and (
            _SET_OPERATION_PATTERN.search(sql) is not None
        )
    for keyword in _SET_OPERATION_KEYWORDS:
        offset: int = folded.find(keyword)
        while offset >= 0:
            if _SET_OPERATION_PATTERN.match(sql, offset) is not None:
                return True
            offset = folded.find(keyword, offset + 1)
    return False
