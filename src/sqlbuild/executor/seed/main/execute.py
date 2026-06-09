"""Seed execution."""

from __future__ import annotations

import time
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.models import SeedPlanEntry
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.seed.constants import SEED_LOAD_FAILED_CODE
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.helpers.naming import resolve_relation_location_qualified_name


def execute_seed(
    *,
    seed_entry: SeedPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    statement_recorder: StatementRecorder,
) -> SeedExecutionResult:
    """Load one seed into the warehouse."""

    start: float = time.monotonic()
    target_qualified: str = resolve_relation_location_qualified_name(
        adapter=adapter, location=seed_entry.destination
    )
    try:
        adapter.ensure_schema(
            connection,
            database=seed_entry.destination.database,
            schema=seed_entry.destination.schema,
            statement_recorder=statement_recorder,
        )
        adapter.load_seed(
            connection,
            target=target_qualified,
            file_path=seed_entry.file_path,
            columns=seed_entry.columns,
            csv_settings=seed_entry.csv_settings,
            replace=True,
            statement_recorder=statement_recorder,
        )
    except Exception as exc:
        return SeedExecutionResult(
            seed_name=seed_entry.name,
            status=ExecutionStatus.FAILED,
            duration_ms=int((time.monotonic() - start) * 1000),
            lifecycle_events=statement_recorder.snapshot(),
            error_code=SEED_LOAD_FAILED_CODE,
            error_message=str(exc),
        )
    return SeedExecutionResult(
        seed_name=seed_entry.name,
        status=ExecutionStatus.SUCCESS,
        duration_ms=int((time.monotonic() - start) * 1000),
        lifecycle_events=statement_recorder.snapshot(),
    )
