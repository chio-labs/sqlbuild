"""Native reference resolution and generic executable-SQL callback support."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator

import sqlbuild._native as _native
from sqlbuild._native import apply_deferred_locations as apply_deferred_locations
from sqlbuild._native import resolve_dbt_ref_references as resolve_dbt_ref_references
from sqlbuild._native import resolve_ref_references as resolve_ref_references
from sqlbuild._native import resolve_table_function_references as resolve_table_function_references
from sqlbuild._native import resolve_udf_references as resolve_udf_references
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.compile.types import (
    CompiledFunctionView,
    CompiledModelView,
    CompiledSeedView,
)
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


def build_model_locations(
    models: tuple[CompiledModelView, ...],
) -> dict[str, CompiledRelationLocation]:
    """Build a lookup of model name to compiled relation location."""

    return {model.name: model.destination for model in models}


def build_seed_locations(
    seeds: tuple[CompiledSeedView, ...],
) -> dict[str, CompiledRelationLocation]:
    """Build a lookup of seed name to compiled relation location."""

    return {seed.name: seed.destination for seed in seeds}


def build_function_locations(
    functions: tuple[CompiledFunctionView, ...],
) -> dict[str, CompiledRelationLocation]:
    """Build a lookup of function name to compiled relation location."""

    return {function.name: function.destination for function in functions}
