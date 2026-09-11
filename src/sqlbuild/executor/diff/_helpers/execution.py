"""Per-model diff execution."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import (
    RowDiffCoverage,
    RowDiffResult,
    RowDiffSampling,
    RowDiffTolerances,
    SchemaDiffResult,
)
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.diff._helpers.bounds import resolve_bounded_cursors
from sqlbuild.executor.diff._helpers.config import (
    parse_row_diff_tolerances,
    resolve_row_diff_sampling,
)
from sqlbuild.executor.diff._helpers.selection import (
    get_row_diff_exclude_columns,
    get_unique_key,
    qualified_name,
)
from sqlbuild.executor.diff.models import DiffExecutionOptions, ModelDiffResult


def execute_model_diff(
    *,
    adapter: BaseAdapter,
    connection: Any,
    name: str,
    left_model: Any,
    right_model: Any,
    options: DiffExecutionOptions,
) -> ModelDiffResult:
    """Execute schema and optional row diff for one model pair."""

    left_relation: str = qualified_name(adapter=adapter, model=left_model)
    right_relation: str = qualified_name(adapter=adapter, model=right_model)
    unique_key: tuple[str, ...] = ()
    if _model_has_unique_key(right_model):
        unique_key = get_unique_key(right_model)
    schema_result: SchemaDiffResult = adapter.diff_schema(
        connection=connection,
        left=left_relation,
        right=right_relation,
    )
    if options.max_columns is not None:
        observed_columns: int = max(
            schema_result.left_column_count,
            schema_result.right_column_count,
        )
        if observed_columns > options.max_columns:
            raise ExecutorInputError(
                f"model '{name}' has {observed_columns} columns, exceeding --max-columns "
                f"{options.max_columns}",
                code="X304",
            )
    row_result: RowDiffResult | None = None
    unequal_row_samples: tuple[Any, ...] = ()
    left_only_key_samples: tuple[tuple[tuple[str, object], ...], ...] = ()
    right_only_key_samples: tuple[tuple[tuple[str, object], ...], ...] = ()
    bounded_fallback: bool = False
    excluded_columns: tuple[str, ...] = ()
    if not options.schema_only:
        (
            row_result,
            unequal_row_samples,
            left_only_key_samples,
            right_only_key_samples,
            bounded_fallback,
            excluded_columns,
        ) = _execute_model_row_diff(
            adapter=adapter,
            connection=connection,
            name=name,
            left_relation=left_relation,
            right_relation=right_relation,
            right_model=right_model,
            unique_key=unique_key,
            options=options,
        )
        unique_key = get_unique_key(right_model) if not unique_key else unique_key
    return ModelDiffResult(
        name=name,
        left_relation=left_relation,
        right_relation=right_relation,
        unique_key=unique_key,
        schema_result=schema_result,
        row_result=row_result,
        unequal_row_samples=tuple(unequal_row_samples),
        left_only_key_samples=left_only_key_samples,
        right_only_key_samples=right_only_key_samples,
        bounded_fallback=bounded_fallback,
        excluded_columns=excluded_columns,
    )


def _execute_model_row_diff(
    *,
    adapter: BaseAdapter,
    connection: Any,
    name: str,
    left_relation: str,
    right_relation: str,
    right_model: Any,
    unique_key: tuple[str, ...],
    options: DiffExecutionOptions,
) -> tuple[
    RowDiffResult,
    tuple[Any, ...],
    tuple[tuple[tuple[str, object], ...], ...],
    tuple[tuple[tuple[str, object], ...], ...],
    bool,
    tuple[str, ...],
]:
    resolved_unique_key: tuple[str, ...] = unique_key or get_unique_key(right_model)
    excluded_columns: tuple[str, ...] = get_row_diff_exclude_columns(right_model)
    intersection: tuple[str, ...] = tuple(
        key for key in resolved_unique_key if key in excluded_columns
    )
    if intersection:
        columns: str = ", ".join(intersection)
        raise ExecutorInputError(
            f"model '{name}' row_diff_exclude_columns intersects unique_key: {columns}",
            code="X302",
        )
    cursor_column: str | None
    start_cursor: Any | None
    end_cursor: Any | None
    bounded_fallback: bool
    cursor_column, start_cursor, end_cursor, bounded_fallback = resolve_bounded_cursors(
        model=right_model,
        bounded=options.bounded,
    )
    tolerances: RowDiffTolerances = parse_row_diff_tolerances(
        raw=right_model.config.values.get("row_diff_tolerances"),
        label=f"model '{name}' row_diff_tolerances",
    )
    sampling: RowDiffSampling | None = resolve_row_diff_sampling(
        raw_row_limit=right_model.config.values.get("row_diff_sample_rows"),
        raw_seed=right_model.config.values.get("row_diff_sample_seed"),
        override=options.sampling_override,
        label=f"model '{name}'",
    )
    tolerances = replace(tolerances, sampling=sampling)
    left_coverage: RowDiffCoverage = adapter.inspect_row_diff_coverage(
        connection=connection,
        relation=left_relation,
        cursor_column=cursor_column,
        start_cursor=start_cursor,
        end_cursor=end_cursor,
    )
    right_coverage: RowDiffCoverage = adapter.inspect_row_diff_coverage(
        connection=connection,
        relation=right_relation,
        cursor_column=cursor_column,
        start_cursor=start_cursor,
        end_cursor=end_cursor,
    )
    row_result: RowDiffResult = adapter.diff_rows(
        connection=connection,
        left=left_relation,
        right=right_relation,
        unique_key=resolved_unique_key,
        excluded_columns=excluded_columns,
        tolerances=tolerances,
        cursor_column=cursor_column,
        start_cursor=start_cursor,
        end_cursor=end_cursor,
    )
    row_result = replace(
        row_result,
        left_coverage=left_coverage,
        right_coverage=right_coverage,
        cursor_column=cursor_column,
        cursor_start=start_cursor.value if start_cursor is not None else None,
        cursor_end=end_cursor.value if end_cursor is not None else None,
    )
    unequal_row_samples: tuple[Any, ...] = ()
    left_only_key_samples: tuple[tuple[tuple[str, object], ...], ...] = ()
    right_only_key_samples: tuple[tuple[tuple[str, object], ...], ...] = ()
    if options.collect_samples and row_result.unequal_count > 0:
        unequal_row_samples = adapter.sample_unequal_rows(
            connection=connection,
            left=left_relation,
            right=right_relation,
            unique_key=resolved_unique_key,
            excluded_columns=excluded_columns,
            tolerances=tolerances,
            cursor_column=cursor_column,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
            limit=options.max_column_examples * 5,
        )
    if options.collect_samples and row_result.left_only_count > 0:
        left_only_key_samples = adapter.sample_side_only_rows(
            connection=connection,
            left=left_relation,
            right=right_relation,
            unique_key=resolved_unique_key,
            side="left",
            cursor_column=cursor_column,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
            limit=options.max_row_only_examples,
            sampling=sampling,
        )
    if options.collect_samples and row_result.right_only_count > 0:
        right_only_key_samples = adapter.sample_side_only_rows(
            connection=connection,
            left=left_relation,
            right=right_relation,
            unique_key=resolved_unique_key,
            side="right",
            cursor_column=cursor_column,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
            limit=options.max_row_only_examples,
            sampling=sampling,
        )
    return (
        row_result,
        unequal_row_samples,
        left_only_key_samples,
        right_only_key_samples,
        bounded_fallback,
        excluded_columns,
    )


def _model_has_unique_key(model: Any) -> bool:
    raw: object | None = model.config.values.get("unique_key")
    if isinstance(raw, str):
        return bool(raw)
    if isinstance(raw, list | tuple):
        return any(isinstance(item, str) and item for item in raw)
    return False
