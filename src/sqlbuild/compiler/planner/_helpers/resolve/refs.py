"""Ref and dbt_ref resolution with optional cursor-filtered subquery wrapping."""

from __future__ import annotations

import re

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledRelationLocation,
    CompiledSeed,
)
from sqlbuild.compiler.planner.constants import (
    SQL_ALIAS_BOUNDARY_CHARACTERS,
    SQL_ALIAS_KEYWORD,
    SQL_FUNCTION_CALL_OPEN_PAREN,
    SQL_IDENTIFIER_LEADING_CHARACTERS,
)
from sqlbuild.compiler.planner.models import CursorBounds
from sqlbuild.compiler.references.main._quoted_reference_call_pattern import (
    quoted_reference_call_pattern,
)
from sqlbuild.compiler.references.main.reference_call_prefix_pattern_text import (
    reference_call_prefix_pattern_text,
)
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver, SqlReferenceKind
from sqlbuild.compiler.sql_analysis.main._find_matching_paren import find_matching_paren

_REF_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.REF)
_SEED_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.SEED)
_DBT_REF_PATTERN: re.Pattern[str] = re.compile(
    rf'{reference_call_prefix_pattern_text(SqlReferenceKind.DBT_REF)}\s*"([^"]+)"\s*'
    r'(?:,\s*"([^"]+)"\s*)?\)',
    re.IGNORECASE,
)
_UDF_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.UDF)
_TABLE_FUNCTION_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(
    SqlReferenceKind.TABLE_FUNCTION
)
_CLAUSE_KEYWORDS: frozenset[str] = frozenset(
    {
        "WHERE",
        "JOIN",
        "INNER",
        "LEFT",
        "RIGHT",
        "FULL",
        "CROSS",
        "ON",
        "GROUP",
        "ORDER",
        "HAVING",
        "LIMIT",
        "UNION",
        "QUALIFY",
    }
)


def resolve_ref_references(
    *,
    query_sql: str,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    cursor_bounds: CursorBounds | None,
    cursor_inputs: dict[str, str],
    adapter: BaseAdapter,
    cursor_type: str | None,
    lower_bound_inclusive: bool,
) -> str:
    """Replace all __ref() and __seed() calls with qualified names or cursor subqueries."""

    def _replace_ref(match: re.Match[str]) -> str:
        ref_name: str = match.group(1)
        target: CompiledRelationLocation | None = model_locations.get(ref_name)
        if target is None:
            return match.group(0)
        qualified_name: str = resolve_relation_location_qualified_name(
            adapter=adapter, location=target
        )
        if cursor_bounds is None:
            return qualified_name
        cursor_column: str | None = cursor_inputs.get(ref_name)
        if cursor_column is None:
            return qualified_name
        has_user_alias: bool = _has_following_alias(sql=query_sql, start=match.end())
        return _build_cursor_subquery(
            qualified_name=qualified_name,
            cursor_column=cursor_column,
            bounds=cursor_bounds,
            adapter=adapter,
            cursor_type=cursor_type,
            lower_bound_inclusive=lower_bound_inclusive,
            inject_alias=not has_user_alias,
        )

    def _replace_seed(match: re.Match[str]) -> str:
        seed_name: str = match.group(1)
        target: CompiledRelationLocation | None = seed_locations.get(seed_name)
        if target is None:
            return match.group(0)
        return resolve_relation_location_qualified_name(adapter=adapter, location=target)

    return _SEED_PATTERN.sub(_replace_seed, _REF_PATTERN.sub(_replace_ref, query_sql))


def resolve_dbt_ref_references(
    *, query_sql: str, external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None
) -> str:
    """Replace all __dbt_ref() calls with external relation names."""

    def _replace_dbt_ref(match: re.Match[str]) -> str:
        if external_sql_reference_resolver is None:
            return match.group(0)
        first_arg: str = match.group(1)
        second_arg: str | None = match.group(2)
        relation_name: str | None = external_sql_reference_resolver.resolve_reference(
            ref_kind="dbt_ref",
            ref_package=first_arg if second_arg is not None else None,
            ref_name=second_arg if second_arg is not None else first_arg,
        )
        return match.group(0) if relation_name is None else relation_name

    return _DBT_REF_PATTERN.sub(_replace_dbt_ref, query_sql)


def resolve_udf_references(
    *,
    query_sql: str,
    function_locations: dict[str, CompiledRelationLocation],
    adapter: BaseAdapter,
) -> str:
    """Replace __udf() calls with adapter-specific scalar UDF calls."""

    parts: list[str] = []
    last_index: int = 0
    match: re.Match[str]
    for match in _UDF_PATTERN.finditer(query_sql):
        parts.append(query_sql[last_index : match.start()])
        function_name: str = match.group(1)
        target: CompiledRelationLocation | None = function_locations.get(function_name)
        if target is None or target.qualified_name is None:
            parts.append(match.group(0))
            last_index = match.end()
            continue

        call_suffix_start: int = _skip_whitespace(sql=query_sql, start=match.end())
        if (
            call_suffix_start >= len(query_sql)
            or query_sql[call_suffix_start] != SQL_FUNCTION_CALL_OPEN_PAREN
        ):
            parts.append(match.group(0))
            last_index = match.end()
            continue

        call_suffix_end: int = find_matching_paren(
            sql=query_sql,
            open_paren_index=call_suffix_start,
            context="SQL UDF call",
        )
        call_suffix_sql: str = query_sql[call_suffix_start : call_suffix_end + 1]
        parts.append(
            adapter.render_udf_call(
                target=target.qualified_name,
                call_suffix_sql=call_suffix_sql,
            )
        )
        last_index = call_suffix_end + 1

    parts.append(query_sql[last_index:])
    return "".join(parts)


def _skip_whitespace(*, sql: str, start: int) -> int:
    index: int = start
    while index < len(sql) and sql[index].isspace():
        index += 1
    return index


def resolve_table_function_references(
    *,
    query_sql: str,
    function_locations: dict[str, CompiledRelationLocation],
    adapter: BaseAdapter,
) -> str:
    """Replace __table_fn() calls with adapter-specific table function calls."""

    parts: list[str] = []
    last_index: int = 0
    match: re.Match[str]
    for match in _TABLE_FUNCTION_PATTERN.finditer(query_sql):
        parts.append(query_sql[last_index : match.start()])
        function_name: str = match.group(1)
        target: CompiledRelationLocation | None = function_locations.get(function_name)
        if target is None or target.qualified_name is None:
            parts.append(match.group(0))
            last_index = match.end()
            continue

        call_suffix_start: int = _skip_whitespace(sql=query_sql, start=match.end())
        if (
            call_suffix_start >= len(query_sql)
            or query_sql[call_suffix_start] != SQL_FUNCTION_CALL_OPEN_PAREN
        ):
            parts.append(match.group(0))
            last_index = match.end()
            continue

        call_suffix_end: int = find_matching_paren(
            sql=query_sql,
            open_paren_index=call_suffix_start,
            context="SQL table function call",
        )
        call_suffix_sql: str = query_sql[call_suffix_start : call_suffix_end + 1]
        parts.append(
            adapter.render_table_function_call(
                target=target.qualified_name,
                call_suffix_sql=call_suffix_sql,
            )
        )
        last_index = call_suffix_end + 1

    parts.append(query_sql[last_index:])
    return "".join(parts)


def _build_cursor_subquery(
    *,
    qualified_name: str,
    cursor_column: str,
    bounds: CursorBounds,
    adapter: BaseAdapter,
    cursor_type: str | None,
    lower_bound_inclusive: bool,
    inject_alias: bool,
) -> str:
    """Wrap a qualified name in a cursor-filtered subquery."""

    lower_operator: str = ">=" if lower_bound_inclusive else ">"
    start_literal: str = adapter.render_cursor_bound_literal(
        value=bounds.start, cursor_type=cursor_type
    )
    end_literal: str = adapter.render_cursor_bound_literal(
        value=bounds.end, cursor_type=cursor_type
    )
    derived_alias: str = (
        " AS __cursor_ref" if inject_alias and adapter.requires_derived_table_aliases() else ""
    )
    return (
        f"(SELECT * FROM {qualified_name}"
        f" WHERE {cursor_column} {lower_operator} {start_literal}"
        f" AND {cursor_column} < {end_literal}){derived_alias}"
    )


def _has_following_alias(*, sql: str, start: int) -> bool:
    index: int = _skip_whitespace(sql=sql, start=start)
    if index >= len(sql) or sql[index] in SQL_ALIAS_BOUNDARY_CHARACTERS:
        return False
    if sql[index : index + 2].upper() == SQL_ALIAS_KEYWORD:
        after_as: int = _skip_whitespace(sql=sql, start=index + 2)
        return after_as < len(sql) and (
            sql[after_as].isalpha() or sql[after_as] in SQL_IDENTIFIER_LEADING_CHARACTERS
        )
    if not (sql[index].isalpha() or sql[index] in SQL_IDENTIFIER_LEADING_CHARACTERS):
        return False
    match: re.Match[str] | None = re.match(r"[A-Za-z_][A-Za-z0-9_]*|\[[^\]]+\]", sql[index:])
    if match is None:
        return False
    token: str = match.group(0).strip("[]").upper()
    return token not in _CLAUSE_KEYWORDS


def build_model_locations(
    models: tuple[CompiledModel, ...],
) -> dict[str, CompiledRelationLocation]:
    """Build a lookup of model name to compiled relation location."""

    return {model.name: model.destination for model in models}


def build_seed_locations(
    seeds: tuple[CompiledSeed, ...],
) -> dict[str, CompiledRelationLocation]:
    """Build a lookup of seed name to compiled relation location."""

    return {seed.name: seed.destination for seed in seeds}


def build_function_locations(
    functions: tuple[CompiledFunction, ...],
) -> dict[str, CompiledRelationLocation]:
    """Build a lookup of function name to compiled relation location."""

    return {function.name: function.destination for function in functions}


def apply_deferred_locations(
    *,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    deferred_locations: dict[str, CompiledRelationLocation],
    selected_keys: frozenset[CompiledObjectKey],
) -> tuple[dict[str, CompiledRelationLocation], dict[str, CompiledRelationLocation]]:
    """Return model/seed locations with non-selected entries pointed at deferred targets."""

    selected_names: frozenset[str] = frozenset(k.name for k in selected_keys)
    updated_model_locations: dict[str, CompiledRelationLocation] = dict(model_locations)
    updated_seed_locations: dict[str, CompiledRelationLocation] = dict(seed_locations)
    name: str
    deferred_location: CompiledRelationLocation
    for name, deferred_location in deferred_locations.items():
        if name in selected_names:
            continue
        if name in updated_model_locations:
            updated_model_locations[name] = deferred_location
        if name in updated_seed_locations:
            updated_seed_locations[name] = deferred_location
    return updated_model_locations, updated_seed_locations
