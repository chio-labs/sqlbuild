"""Validation helpers for executable SQL resolution."""

from __future__ import annotations

import re

from sqlbuild.compiler.references._helpers.patterns import reference_call_prefix_pattern_text
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.main._skip_block_comment import skip_block_comment
from sqlbuild.compiler.sql_analysis.main._skip_line_comment import skip_line_comment
from sqlbuild.compiler.sql_analysis.main._skip_quoted_text import skip_quoted_text

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
_SQL_QUOTE_TOKENS: frozenset[str] = frozenset({"'", '"', "`"})


def assert_no_unresolved_sql_markers(*, sql: str, context: str) -> None:
    """Fail fast if executable SQL still contains unresolved ref/source markers."""

    if _contains_executable_marker(sql=sql, pattern=_UNRESOLVED_REF_PATTERN, context=context):
        raise _coded_value_error(
            message=f"{context} still contains unresolved "
            f"{SqlReferenceKind.REF.placeholder_call()} markers",
            code="R001",
        )
    if _contains_executable_marker(sql=sql, pattern=_UNRESOLVED_SEED_PATTERN, context=context):
        raise _coded_value_error(
            message=f"{context} still contains unresolved "
            f"{SqlReferenceKind.SEED.placeholder_call()} markers",
            code="R002",
        )
    if _contains_executable_marker(sql=sql, pattern=_UNRESOLVED_SOURCE_PATTERN, context=context):
        raise _coded_value_error(
            message=f"{context} still contains unresolved "
            f"{SqlReferenceKind.SOURCE.placeholder_call()} markers",
            code="R003",
        )
    if _contains_executable_marker(sql=sql, pattern=_UNRESOLVED_UDF_PATTERN, context=context):
        raise _coded_value_error(
            message=f"{context} still contains unresolved "
            f"{SqlReferenceKind.UDF.placeholder_call()} markers",
            code="R004",
        )
    if _contains_executable_marker(
        sql=sql, pattern=_UNRESOLVED_TABLE_FUNCTION_PATTERN, context=context
    ):
        raise _coded_value_error(
            message=f"{context} still contains unresolved "
            f"{SqlReferenceKind.TABLE_FUNCTION.placeholder_call()} markers",
            code="R005",
        )


def _contains_executable_marker(*, sql: str, pattern: re.Pattern[str], context: str) -> bool:
    if pattern.search(sql) is None:
        return False
    index: int = 0
    while index < len(sql):
        if sql[index] in _SQL_QUOTE_TOKENS:
            index = skip_quoted_text(sql=sql, start=index, context=context)
            continue
        if sql.startswith("--", index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment(sql=sql, start=index, context=context)
            continue
        if pattern.match(sql, index) is not None:
            return True
        index += 1
    return False


def _coded_value_error(*, message: str, code: str) -> ValueError:
    error: ValueError = ValueError(message)
    object.__setattr__(error, "message", message)
    object.__setattr__(error, "code", code)
    return error
