"""Table cursor resolution before lifecycle side effects."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.planner.main.execution.future_cursor_warning import (
    future_cursor_cap_warning,
)
from sqlbuild.compiler.planner.models import CursorBounds, ModelPlanEntry
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.run._helpers.validation.cursor_bounds import (
    build_runtime_cursor_spec,
    has_authoritative_cursor_override,
    has_runtime_owned_cursor_watermarks,
    resolve_runtime_cursor_bounds,
    substitute_cursor_sentinels,
)
from sqlbuild.executor.run.models import (
    ModelExecutionResult,
    ModelMaterializationContext,
    TableCursorResolution,
    TableTargets,
)


def resolve_table_cursor(
    *,
    context: ModelMaterializationContext,
    targets: TableTargets,
    is_full_refresh: bool,
) -> TableCursorResolution:
    """Resolve table cursor policy before pre-hook execution."""

    entry: ModelPlanEntry = context.entry
    planned_bounds: CursorBounds | None = entry.microbatch_range or entry.cursor_bounds
    runtime_owned: bool = (
        not is_full_refresh
        and not has_authoritative_cursor_override(entry=entry)
        and has_runtime_owned_cursor_watermarks(entry.cursor_input_relations)
    )
    if not runtime_owned:
        return TableCursorResolution(
            resolved_sql=entry.resolved_sql,
            bounds=planned_bounds,
            warning=future_cursor_cap_warning(planned_bounds),
        )
    if entry.cursor_column is None:
        raise ExecutorInputError("runtime-owned cursor resolution requires cursor_column")
    bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
        adapter=context.adapter,
        connection=context.connection,
        target_relation=targets.target_qualified,
        target_database=targets.target_database,
        target_schema=targets.target_schema,
        target_name=targets.target_table,
        spec=build_runtime_cursor_spec(entry=entry),
        watermark_resolver=context.watermark_resolver,
    )
    if bounds is None:
        raise ExecutorInputError(f"runtime cursor bounds could not be resolved for '{entry.name}'")
    return TableCursorResolution(
        resolved_sql=substitute_cursor_sentinels(sql=entry.resolved_sql, bounds=bounds),
        bounds=bounds,
        warning=future_cursor_cap_warning(bounds),
    )


def result_with_cursor_safety(
    *, result: ModelExecutionResult, entry: ModelPlanEntry
) -> ModelExecutionResult:
    """Attach effective cursor safety evidence to a table result."""

    bounds: CursorBounds | None = entry.microbatch_range or entry.cursor_bounds
    return replace(
        result,
        future_cursor_safety=bounds.future_safety if bounds is not None else None,
    )
