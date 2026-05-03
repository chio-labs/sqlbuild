"""Seed execution."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.models import SeedPlanEntry
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.shared.helpers.naming import build_qualified_name
from sqlbuild.executor.shared.types import ExecutionStatus


def execute_seed(
    *,
    seed_entry: SeedPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    statement_recorder: StatementRecorder,
) -> SeedExecutionResult:
    """Load one seed into the warehouse."""

    target_qualified: str = build_qualified_name(
        database=seed_entry.target.database,
        schema=seed_entry.target.schema,
        name=seed_entry.target.name,
    )
    try:
        adapter.ensure_schema(
            connection,
            database=seed_entry.target.database,
            schema=seed_entry.target.schema,
            statement_recorder=statement_recorder,
        )
        adapter.load_seed(
            connection,
            target=target_qualified,
            file_path=seed_entry.file_path,
            columns=seed_entry.columns,
            replace=True,
            statement_recorder=statement_recorder,
        )
    except Exception as exc:
        return SeedExecutionResult(
            seed_name=seed_entry.name,
            status=ExecutionStatus.FAILED,
            error_message=str(exc),
        )
    return SeedExecutionResult(
        seed_name=seed_entry.name,
        status=ExecutionStatus.SUCCESS,
    )
