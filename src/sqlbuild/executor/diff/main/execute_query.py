"""Execute one prepared query diff."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.diff._helpers.execution import execute_query_diff as _execute_query_diff
from sqlbuild.executor.diff.models import DiffExecutionOptions, ModelDiffResult


def execute_query_diff(
    *,
    adapter: BaseAdapter,
    connection: Any,
    left_relation: str,
    right_relation: str,
    options: DiffExecutionOptions,
) -> ModelDiffResult:
    """Execute one prepared raw-query relation comparison."""

    return _execute_query_diff(
        adapter=adapter,
        connection=connection,
        left_relation=left_relation,
        right_relation=right_relation,
        options=options,
    )
