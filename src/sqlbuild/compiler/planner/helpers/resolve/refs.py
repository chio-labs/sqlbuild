"""Ref and dbt_ref resolution with optional cursor-filtered subquery wrapping."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledRelationTarget,
    CompiledSeed,
)
from sqlbuild.compiler.planner.models import CursorBounds

_REF_PATTERN: re.Pattern[str] = re.compile(r'__ref\("([^"]+)"\)')
_DBT_REF_PATTERN: re.Pattern[str] = re.compile(r'__dbt_ref\("([^"]+)"\)')


def resolve_ref_references(
    *,
    query_sql: str,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    cursor_bounds: CursorBounds | None,
    cursor_inputs: dict[str, str],
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


def _build_cursor_subquery(
    *,
    qualified_name: str,
    cursor_column: str,
    bounds: CursorBounds,
    lower_bound_inclusive: bool,
) -> str:
    """Wrap a qualified name in a cursor-filtered subquery."""

    lower_operator: str = ">=" if lower_bound_inclusive else ">"
    return (
        f"(SELECT * FROM {qualified_name}"
        f" WHERE {cursor_column} {lower_operator} '{bounds.start}'"
        f" AND {cursor_column} < '{bounds.end}')"
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
