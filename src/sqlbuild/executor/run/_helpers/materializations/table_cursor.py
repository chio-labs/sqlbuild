"""Table cursor resolution before lifecycle side effects."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.adapter.relations.main.cached_relation_exists import cached_relation_exists
from sqlbuild.compiler.planner.main.changes.relation_replacement import (
    replaces_incremental_relation,
)
from sqlbuild.compiler.planner.main.cursor_window.empty_cursor_window import empty_cursor_window
from sqlbuild.compiler.planner.main.execution.future_cursor_warning import (
    future_cursor_cap_warning,
)
from sqlbuild.compiler.planner.models import CursorBounds, ModelPlanEntry
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.run._helpers.validation.cursor_bounds import (
    build_runtime_cursor_spec,
    cursor_window_unavailable_error,
    empty_input_rebuild_error,
    has_authoritative_cursor_override,
    has_runtime_owned_cursor_watermarks,
    resolve_runtime_cursor_bounds,
    substitute_cursor_sentinels,
)
from sqlbuild.executor.run.exceptions import EmptyCursorInputsError
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
    try:
        bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
            adapter=context.adapter,
            connection=context.connection,
            target_relation=targets.target_qualified,
            target_database=targets.target_database,
            target_schema=targets.target_schema,
            target_name=targets.target_table,
            spec=build_runtime_cursor_spec(
                entry=entry,
                read_destination_cursor=not replaces_incremental_relation(
                    materialization_type=entry.materialization_type, action=entry.action
                ),
            ),
            watermark_resolver=context.watermark_resolver,
        )
    except EmptyCursorInputsError as exc:
        if cached_relation_exists(
            adapter=context.adapter,
            connection=context.connection,
            database=targets.target_database,
            schema=targets.target_schema,
            name=targets.target_table,
        ):
            raise empty_input_rebuild_error(entry=entry, input_names=exc.input_names) from exc
        return TableCursorResolution(
            resolved_sql=substitute_cursor_sentinels(
                sql=entry.resolved_sql,
                bounds=empty_cursor_window(
                    cursor_type=entry.cursor_type, cursor_start=entry.cursor_start
                ),
            ),
            bounds=None,
            empty_cursor_inputs=exc.input_names,
            waiting_on_empty_inputs=exc.waiting_on_empty_inputs,
        )
    if bounds is None:
        raise cursor_window_unavailable_error(entry=entry)
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
        empty_cursor_inputs=entry.empty_cursor_inputs,
        waiting_on_empty_inputs=entry.waiting_on_empty_inputs,
        future_cursor_safety=bounds.future_safety if bounds is not None else None,
        maximum_start_safety=(bounds.maximum_start_safety if bounds is not None else None),
    )
