"""Execute model diffs across compiled relation locations."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.diff._helpers.execution import execute_model_diff
from sqlbuild.executor.diff._helpers.selection import is_disabled
from sqlbuild.executor.diff.models import DiffExecutionOptions, DiffExecutionResult, ModelDiffResult


def execute_diff(
    *,
    adapter: BaseAdapter,
    connection: Any,
    left_project: Any,
    right_project: Any,
    selected_names: tuple[str, ...],
    options: DiffExecutionOptions,
) -> DiffExecutionResult:
    """Execute schema and optional row diffs for selected model names."""

    left_models: dict[str, Any] = {
        model.name: model for model in left_project.models if not is_disabled(model)
    }
    right_models: dict[str, Any] = {
        model.name: model for model in right_project.models if not is_disabled(model)
    }
    if options.max_models is not None and len(selected_names) > options.max_models:
        raise ExecutorInputError(
            f"diff selected {len(selected_names)} models, exceeding --max-models "
            f"{options.max_models}",
            code="X303",
        )
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
                options=options,
            )
        )
    return DiffExecutionResult(model_results=tuple(results))
