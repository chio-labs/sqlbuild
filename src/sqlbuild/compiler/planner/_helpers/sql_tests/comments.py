"""SQL comment handling for textual unit-test fallback resolution."""

from __future__ import annotations

import re

_SQL_NON_CODE_PATTERN: re.Pattern[str] = re.compile(
    r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|"
    r"\$\$.*?\$\$|--[^\n]*|/\*.*?\*/",
    re.DOTALL,
)


def uncommented_pattern_matches(*, pattern: re.Pattern[str], sql: str) -> tuple[re.Match[str], ...]:
    """Find pattern matches outside SQL comments and quoted values."""

    return uncommented_matches_by_pattern(patterns=(pattern,), sql=sql)[0]


def uncommented_matches_by_pattern(
    *, patterns: tuple[re.Pattern[str], ...], sql: str
) -> tuple[tuple[re.Match[str], ...], ...]:
    """Find matches for multiple patterns with one protected-region scan."""

    if all(pattern.search(sql) is None for pattern in patterns):
        return tuple(() for _pattern in patterns)
    protected_ranges: tuple[tuple[int, int], ...] = tuple(
        (match.start(), match.end()) for match in _SQL_NON_CODE_PATTERN.finditer(sql)
    )

    def _matches(pattern: re.Pattern[str]) -> tuple[re.Match[str], ...]:
        protected_index: int = 0
        matches: list[re.Match[str]] = []
        match: re.Match[str]
        for match in pattern.finditer(sql):
            while (
                protected_index < len(protected_ranges)
                and protected_ranges[protected_index][1] <= match.start()
            ):
                protected_index += 1
            if (
                protected_index == len(protected_ranges)
                or match.start() < protected_ranges[protected_index][0]
            ):
                matches.append(match)
        return tuple(matches)

    return tuple(_matches(pattern) for pattern in patterns)
