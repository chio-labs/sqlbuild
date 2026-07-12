"""Execute model diffs across compiled relation locations."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.executor.diff.helpers.execution import execute_model_diff
from sqlbuild.executor.diff.helpers.selection import is_disabled
from sqlbuild.executor.diff.models import DiffExecutionResult, ModelDiffResult
from sqlbuild.executor.exceptions import ExecutorInputError


def execute_diff(
    *,
    adapter: BaseAdapter,
    connection: Any,
    left_project: Any,
    right_project: Any,
    selected_names: tuple[str, ...],
    schema_only: bool,
    bounded: str | None = None,
    collect_samples: bool = False,
    max_column_examples: int = 20,
    max_row_only_examples: int = 20,
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
            raise ExecutorInputError(
                f"diff selected model '{name}' does not exist in both environments",
                code="X301",
            )

        results.append(
            execute_model_diff(
                adapter=adapter,
                connection=connection,
                name=name,
                left_model=left_model,
                right_model=right_model,
                schema_only=schema_only,
                bounded=bounded,
                collect_samples=collect_samples,
                max_column_examples=max_column_examples,
                max_row_only_examples=max_row_only_examples,
            )
        )
    return DiffExecutionResult(model_results=tuple(results))
