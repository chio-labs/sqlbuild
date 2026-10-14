"""Native reference resolution and generic executable-SQL callback support."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator

import sqlbuild._native as _native
from sqlbuild._native import apply_deferred_locations as apply_deferred_locations
from sqlbuild._native import build_function_locations as build_function_locations
from sqlbuild._native import build_model_locations as build_model_locations
from sqlbuild._native import build_seed_locations as build_seed_locations
from sqlbuild._native import resolve_dbt_ref_references as resolve_dbt_ref_references
from sqlbuild._native import resolve_ref_references as resolve_ref_references
from sqlbuild._native import resolve_table_function_references as resolve_table_function_references
from sqlbuild._native import resolve_udf_references as resolve_udf_references
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax

_REFERENCE_SCAN_CONTEXT: str = "SQL reference resolution"


def replace_executable_matches(
    *,
    sql: str,
    pattern: re.Pattern[str],
    replace: Callable[[re.Match[str]], str],
    lexical_syntax: SqlLexicalSyntax,
) -> str:
    """Replace pattern matches in executable SQL, leaving quoted text and comments untouched."""

    parts: list[str] = []
    last_index: int = 0
    for match in _iter_code_matches(
        sql=sql,
        pattern=pattern,
        scanner=_native.SqlCodeScanner(sql, lexical_syntax.native_mapping, _REFERENCE_SCAN_CONTEXT),
    ):
        parts.append(sql[last_index : match.start()])
        parts.append(replace(match))
        last_index = match.end()
    parts.append(sql[last_index:])
    return "".join(parts)


def _iter_code_matches(
    *, sql: str, pattern: re.Pattern[str], scanner: _native.SqlCodeScanner
) -> Iterator[re.Match[str]]:
    index: int = 0
    while index < len(sql):
        non_code_end: int | None = scanner.non_code_end(index)
        if non_code_end is not None:
            index = non_code_end
            continue
        match: re.Match[str] | None = pattern.match(sql, index)
        if match is None:
            index += 1
            continue
        yield match
        index = match.end()
