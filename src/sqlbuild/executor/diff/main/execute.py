"""Execute model diffs across compiled environments."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RowDiffResult, SchemaDiffResult
from sqlbuild.executor.diff.helpers.bounds import resolve_bounded_cursors
from sqlbuild.executor.diff.helpers.config import parse_row_diff_tolerances
from sqlbuild.executor.diff.helpers.selection import (
    get_row_diff_exclude_columns,
    get_unique_key,
    is_disabled,
    qualified_name,
)
from sqlbuild.executor.diff.models import DiffExecutionResult, ModelDiffResult


def execute_diff(
    *,
    adapter: BaseAdapter,
    connection: Any,
    left_project: Any,
    right_project: Any,
    selected_names: tuple[str, ...],
    schema_only: bool,
    bounded: str | None = None,
) -> DiffExecutionResult:
    """Execute schema and optional row diffs for selected model names."""

    left_models: dict[str, Any] = {
        model.name: model for model in left_project.models if not is_disabled(model)
    }
    right_models: dict[str, Any] = {
        model.name: model for model in right_project.models if not is_disabled(model)
    }
    results: list[ModelDiffResult] = []
    name: str
    for name in selected_names:
        left_model: Any | None = left_models.get(name)
        right_model: Any | None = right_models.get(name)
        if left_model is None or right_model is None:
            raise ValueError(f"diff selected model '{name}' does not exist in both environments")

        left_relation: str = qualified_name(left_model)
        right_relation: str = qualified_name(right_model)
        schema_result: SchemaDiffResult = adapter.diff_schema(
            connection,
            left=left_relation,
            right=right_relation,
        )
        row_result: RowDiffResult | None = None
        bounded_fallback: bool = False
        if not schema_only:
            unique_key: tuple[str, ...] = get_unique_key(right_model)
            excluded_columns: tuple[str, ...] = get_row_diff_exclude_columns(right_model)
            intersection: tuple[str, ...] = tuple(
                key for key in unique_key if key in excluded_columns
            )
            if intersection:
                columns: str = ", ".join(intersection)
                raise ValueError(
                    f"model '{name}' row_diff_exclude_columns intersects unique_key: {columns}"
                )
            cursor_column: str | None
            start_cursor: Any | None
            end_cursor: Any | None
            cursor_column, start_cursor, end_cursor, bounded_fallback = resolve_bounded_cursors(
                model=right_model,
                bounded=bounded,
            )
            row_result = adapter.diff_rows(
                connection,
                left=left_relation,
                right=right_relation,
                unique_key=unique_key,
                excluded_columns=excluded_columns,
                tolerances=parse_row_diff_tolerances(
                    right_model.config.values.get("row_diff_tolerances"),
                    label=f"model '{name}' row_diff_tolerances",
                ),
                cursor_column=cursor_column,
                start_cursor=start_cursor,
                end_cursor=end_cursor,
            )
        results.append(
            ModelDiffResult(
                name=name,
                left_relation=left_relation,
                right_relation=right_relation,
                unique_key=unique_key if not schema_only else (),
                schema_result=schema_result,
                row_result=row_result,
                bounded_fallback=bounded_fallback,
                excluded_columns=excluded_columns if not schema_only else (),
            )
        )
    return DiffExecutionResult(model_results=tuple(results))
