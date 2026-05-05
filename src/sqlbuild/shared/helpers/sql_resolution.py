"""Validation helpers for executable SQL resolution."""

from __future__ import annotations

import re

_UNRESOLVED_REF_PATTERN: re.Pattern[str] = re.compile(r"__ref\(")
_UNRESOLVED_SEED_PATTERN: re.Pattern[str] = re.compile(r"__seed\(")
_UNRESOLVED_SOURCE_PATTERN: re.Pattern[str] = re.compile(r"__source\(")
_UNRESOLVED_UDF_PATTERN: re.Pattern[str] = re.compile(r"__udf\(")
_UNRESOLVED_TABLE_FUNCTION_PATTERN: re.Pattern[str] = re.compile(r"__table_function\(")


def assert_no_unresolved_sql_markers(*, sql: str, context: str) -> None:
    """Fail fast if executable SQL still contains unresolved ref/source markers."""

    if _UNRESOLVED_REF_PATTERN.search(sql):
        raise ValueError(f"{context} still contains unresolved __ref() markers")
    if _UNRESOLVED_SEED_PATTERN.search(sql):
        raise ValueError(f"{context} still contains unresolved __seed() markers")
    if _UNRESOLVED_SOURCE_PATTERN.search(sql):
        raise ValueError(f"{context} still contains unresolved __source() markers")
    if _UNRESOLVED_UDF_PATTERN.search(sql):
        raise ValueError(f"{context} still contains unresolved __udf() markers")
    if _UNRESOLVED_TABLE_FUNCTION_PATTERN.search(sql):
        raise ValueError(f"{context} still contains unresolved __table_function() markers")
