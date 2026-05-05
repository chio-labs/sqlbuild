"""Ref and dbt_ref resolution with optional cursor-filtered subquery wrapping."""

from __future__ import annotations

import re

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledRelationTarget,
    CompiledSeed,
)
from sqlbuild.compiler.planner.models import CursorBounds

_REF_PATTERN: re.Pattern[str] = re.compile(r'__ref\("([^"]+)"\)')
_DBT_REF_PATTERN: re.Pattern[str] = re.compile(r'__dbt_ref\("([^"]+)"\)')
_UDF_PATTERN: re.Pattern[str] = re.compile(r'__udf\("([^"]+)"\)')


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
    """Replace all __ref() calls with qualified names or cursor-filtered subqueries."""

    def _replace_ref(match: re.Match[str]) -> str:
        ref_name: str = match.group(1)
        target: CompiledRelationTarget | None = model_targets.get(ref_name)
        if target is None:
            target = seed_targets.get(ref_name)
        if target is None or target.qualified_name is None:
            return match.group(0)
        qualified_name: str = target.qualified_name
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

    return _REF_PATTERN.sub(_replace_ref, query_sql)


def resolve_dbt_ref_references(*, query_sql: str) -> str:
    """Replace all __dbt_ref() calls. Currently stubs with an error marker.

    Full dbt manifest resolution is deferred. Any remaining __dbt_ref() calls
    are left as-is for now; validation at compile time already ensures a
    manifest exists when __dbt_ref is used.
    """

    return query_sql


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
