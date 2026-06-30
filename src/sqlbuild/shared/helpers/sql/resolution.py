"""Validation helpers for executable SQL resolution."""

from __future__ import annotations

import re

from sqlbuild.shared.helpers.sql.reference_patterns import reference_call_prefix_pattern_text
from sqlbuild.shared.types import SqlReferenceKind

_UNRESOLVED_REF_PATTERN: re.Pattern[str] = re.compile(
    reference_call_prefix_pattern_text(SqlReferenceKind.REF)
)
_UNRESOLVED_SEED_PATTERN: re.Pattern[str] = re.compile(
    reference_call_prefix_pattern_text(SqlReferenceKind.SEED)
)
_UNRESOLVED_SOURCE_PATTERN: re.Pattern[str] = re.compile(
    reference_call_prefix_pattern_text(SqlReferenceKind.SOURCE)
)
_UNRESOLVED_UDF_PATTERN: re.Pattern[str] = re.compile(
    reference_call_prefix_pattern_text(SqlReferenceKind.UDF)
)
_UNRESOLVED_TABLE_FUNCTION_PATTERN: re.Pattern[str] = re.compile(
    reference_call_prefix_pattern_text(SqlReferenceKind.TABLE_FUNCTION)
)


def assert_no_unresolved_sql_markers(*, sql: str, context: str) -> None:
    """Fail fast if executable SQL still contains unresolved ref/source markers."""

    if _UNRESOLVED_REF_PATTERN.search(sql):
        raise _coded_value_error(
            f"{context} still contains unresolved "
            f"{SqlReferenceKind.REF.placeholder_call()} markers",
            code="R001",
        )
    if _UNRESOLVED_SEED_PATTERN.search(sql):
        raise _coded_value_error(
            f"{context} still contains unresolved "
            f"{SqlReferenceKind.SEED.placeholder_call()} markers",
            code="R002",
        )
    if _UNRESOLVED_SOURCE_PATTERN.search(sql):
        raise _coded_value_error(
            f"{context} still contains unresolved "
            f"{SqlReferenceKind.SOURCE.placeholder_call()} markers",
            code="R003",
        )
    if _UNRESOLVED_UDF_PATTERN.search(sql):
        raise _coded_value_error(
            f"{context} still contains unresolved "
            f"{SqlReferenceKind.UDF.placeholder_call()} markers",
            code="R004",
        )
    if _UNRESOLVED_TABLE_FUNCTION_PATTERN.search(sql):
        raise _coded_value_error(
            f"{context} still contains unresolved "
            f"{SqlReferenceKind.TABLE_FUNCTION.placeholder_call()} markers",
            code="R005",
        )


def _coded_value_error(message: str, *, code: str) -> ValueError:
    error: ValueError = ValueError(message)
    object.__setattr__(error, "message", message)
    object.__setattr__(error, "code", code)
    return error
