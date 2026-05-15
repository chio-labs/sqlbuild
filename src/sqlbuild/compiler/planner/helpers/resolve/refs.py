"""Ref and dbt_ref resolution with optional cursor-filtered subquery wrapping."""

from __future__ import annotations

import re

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledRelationTarget,
    CompiledSeed,
)
from sqlbuild.compiler.planner.models import CursorBounds
from sqlbuild.shared.helpers.naming import resolve_target_qualified_name
from sqlbuild.shared.helpers.sql_reference_patterns import (
    quoted_reference_call_pattern,
    quoted_reference_call_pattern_text,
    reference_call_prefix_pattern_text,
)
from sqlbuild.shared.types import ExternalSqlReferenceResolver, SqlReferenceKind

_REF_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.REF)
_SEED_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.SEED)
_DBT_REF_PATTERN: re.Pattern[str] = re.compile(
    rf'{reference_call_prefix_pattern_text(SqlReferenceKind.DBT_REF)}\s*"([^"]+)"\s*'
    r'(?:,\s*"([^"]+)"\s*)?\)',
    re.IGNORECASE,
)
_UDF_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.UDF)
_TABLE_FUNCTION_CALL_PATTERN: re.Pattern[str] = re.compile(
    rf"{quoted_reference_call_pattern_text(SqlReferenceKind.TABLE_FUNCTION)}\s*"
    r"\(([^()]*)\)"
)


def resolve_ref_references(
    *,
    query_sql: str,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    cursor_bounds: CursorBounds | None,
    cursor_inputs: dict[str, str],
    adapter: BaseAdapter,
    cursor_type: str | None,
    lower_bound_inclusive: bool,
) -> str:
    """Replace all __ref() and __seed() calls with qualified names or cursor subqueries."""

    def _replace_ref(match: re.Match[str]) -> str:
        ref_name: str = match.group(1)
        target: CompiledRelationTarget | None = model_targets.get(ref_name)
        if target is None:
            return match.group(0)
        qualified_name: str = resolve_target_qualified_name(adapter=adapter, target=target)
        if cursor_bounds is None:
            return qualified_name
        cursor_column: str | None = cursor_inputs.get(ref_name)
        if cursor_column is None:
            return qualified_name
        return _build_cursor_subquery(
            qualified_name=qualified_name,
            cursor_column=cursor_column,
            bounds=cursor_bounds,
            adapter=adapter,
            cursor_type=cursor_type,
            lower_bound_inclusive=lower_bound_inclusive,
        )

    def _replace_seed(match: re.Match[str]) -> str:
        seed_name: str = match.group(1)
        target: CompiledRelationTarget | None = seed_targets.get(seed_name)
        if target is None:
            return match.group(0)
        return resolve_target_qualified_name(adapter=adapter, target=target)

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
    *, query_sql: str, function_targets: dict[str, CompiledRelationTarget]
) -> str:
    """Replace all __udf() calls with qualified function names."""

    def _replace_udf(match: re.Match[str]) -> str:
        function_name: str = match.group(1)
        target: CompiledRelationTarget | None = function_targets.get(function_name)
        if target is None or target.qualified_name is None:
            return match.group(0)
        return target.qualified_name

    return _UDF_PATTERN.sub(_replace_udf, query_sql)


def resolve_table_function_references(
    *,
    query_sql: str,
    function_targets: dict[str, CompiledRelationTarget],
    adapter: BaseAdapter,
) -> str:
    """Replace __table_fn() calls with adapter-specific table function calls."""

    def _replace_table_function(match: re.Match[str]) -> str:
        function_name: str = match.group(1)
        arguments_sql: str = match.group(2)
        target: CompiledRelationTarget | None = function_targets.get(function_name)
        if target is None or target.qualified_name is None:
            return match.group(0)
        return adapter.render_table_function_call(
            target=target.qualified_name,
            arguments_sql=arguments_sql,
        )

    return _TABLE_FUNCTION_CALL_PATTERN.sub(_replace_table_function, query_sql)


def _build_cursor_subquery(
    *,
    qualified_name: str,
    cursor_column: str,
    bounds: CursorBounds,
    adapter: BaseAdapter,
    cursor_type: str | None,
    lower_bound_inclusive: bool,
) -> str:
    """Wrap a qualified name in a cursor-filtered subquery."""

    lower_operator: str = ">=" if lower_bound_inclusive else ">"
    start_literal: str = adapter.render_cursor_bound_literal(bounds.start, cursor_type)
    end_literal: str = adapter.render_cursor_bound_literal(bounds.end, cursor_type)
    return (
        f"(SELECT * FROM {qualified_name}"
        f" WHERE {cursor_column} {lower_operator} {start_literal}"
        f" AND {cursor_column} < {end_literal})"
    )


def build_model_targets(
    models: tuple[CompiledModel, ...],
) -> dict[str, CompiledRelationTarget]:
    """Build a lookup of model name to compiled relation target."""

    return {model.name: model.target for model in models}


def build_seed_targets(
    seeds: tuple[CompiledSeed, ...],
) -> dict[str, CompiledRelationTarget]:
    """Build a lookup of seed name to compiled relation target."""

    return {seed.name: seed.target for seed in seeds}


def build_function_targets(
    functions: tuple[CompiledFunction, ...],
) -> dict[str, CompiledRelationTarget]:
    """Build a lookup of function name to compiled relation target."""

    return {function.name: function.target for function in functions}


def apply_deferred_targets(
    *,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    deferred_targets: dict[str, CompiledRelationTarget],
    selected_keys: frozenset[CompiledObjectKey],
) -> None:
    """Replace non-selected model/seed targets with deferred environment targets."""

    selected_names: frozenset[str] = frozenset(k.name for k in selected_keys)
    name: str
    deferred_target: CompiledRelationTarget
    for name, deferred_target in deferred_targets.items():
        if name in selected_names:
            continue
        if name in model_targets:
            model_targets[name] = deferred_target
        if name in seed_targets:
            seed_targets[name] = deferred_target
