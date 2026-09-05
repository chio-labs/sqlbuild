"""SQL comment handling for textual unit-test fallback resolution."""

from __future__ import annotations

import re
from collections.abc import Callable

from sqlbuild.adapter.contract.types import BuiltinAdapter

_SQL_NON_CODE_PATTERN: re.Pattern[str] = re.compile(
    r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|"
    r"\$\$.*?\$\$|--[^\n]*|/\*.*?\*/",
    re.DOTALL,
)
_SNOWFLAKE_STARTS_WITH_PATTERN: re.Pattern[str] = re.compile(
    r"\bSTARTS_WITH(?=\s*\()", re.IGNORECASE
)


def uncommented_pattern_matches(*, pattern: re.Pattern[str], sql: str) -> tuple[re.Match[str], ...]:
    """Find pattern matches outside SQL comments and quoted values."""

    return uncommented_matches_by_pattern(patterns=(pattern,), sql=sql)[0]


def uncommented_matches_by_pattern(
    *, patterns: tuple[re.Pattern[str], ...], sql: str
) -> tuple[tuple[re.Match[str], ...], ...]:
    """Find matches for multiple patterns with one protected-region scan."""

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


def replace_uncommented_pattern(
    *, pattern: re.Pattern[str], replacement: Callable[[re.Match[str]], str], sql: str
) -> str:
    """Replace pattern matches outside comments while preserving original comments."""

    result: str = sql
    for match in reversed(uncommented_pattern_matches(pattern=pattern, sql=sql)):
        result = f"{result[: match.start()]}{replacement(match)}{result[match.end() :]}"
    return result


def restore_sql_test_dialect_function_names(*, sql: str, dialect: str | None) -> str:
    """Restore warehouse-supported spellings changed by SQL analysis formatting."""

    if dialect != BuiltinAdapter.SNOWFLAKE:
        return sql
    return replace_uncommented_pattern(
        pattern=_SNOWFLAKE_STARTS_WITH_PATTERN,
        replacement=lambda _match: "STARTSWITH",
        sql=sql,
    )
