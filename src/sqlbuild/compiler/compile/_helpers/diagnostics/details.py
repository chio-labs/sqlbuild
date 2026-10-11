"""Column suggestions and unknown-column parsing for resource SQL diagnostics."""

from __future__ import annotations

import re
from typing import Any

_MIN_ABBREVIATION_LENGTH: int = 3
_MAX_EDIT_DISTANCE: int = 2
_MISSING: re.Pattern[str] = re.compile(r"Unknown column '([^']+)'(?: in table '([^']+)')?")


def column_distance(*, left: str, right: str) -> int:
    """Levenshtein distance, also used to order schema evidence."""
    left, right = left.casefold(), right.casefold()
    row: list[int] = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        following: list[int] = [i]
        for j, b in enumerate(right, 1):
            following.append(min(following[-1] + 1, row[j] + 1, row[j - 1] + (a != b)))
        row = following
    return row[-1]


def ordered_columns(*, name: str, columns: dict[str, str]) -> list[str]:
    return sorted(
        columns,
        key=lambda value: (
            column_distance(left=name, right=value) / max(len(name), len(value), 1),
            value,
        ),
    )


def closest_column(*, name: str, columns: dict[str, str]) -> str | None:
    candidates: list[str] = ordered_columns(name=name, columns=columns)
    for candidate in candidates:
        distance: int = column_distance(left=name, right=candidate)
        remaining: Any = iter(candidate.casefold())
        abbreviation: bool = (
            len(name) >= _MIN_ABBREVIATION_LENGTH
            and candidate[:1].casefold() == name[:1].casefold()
            and candidate[-1:].casefold() == name[-1:].casefold()
            and all(character in remaining for character in name.casefold())
        )
        if distance <= _MAX_EDIT_DISTANCE or abbreviation:
            return candidate
    return None


def missing_column(message: str) -> tuple[str, str | None] | None:
    match: re.Match[str] | None = _MISSING.search(message)
    return (match.group(1), match.group(2)) if match else None
