"""Seed execution."""

from __future__ import annotations

import time
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.models import SeedPlanEntry
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.seed.constants import SEED_LOAD_FAILED_CODE
from sqlbuild.executor.seed.helpers.fingerprinting import try_write_seed_fingerprint
from sqlbuild.executor.types import ExecutionStatus
from sqlbuild.shared.helpers.identity.naming import resolve_relation_location_qualified_name


def execute_seed(
    *,
    seed_entry: SeedPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    statement_recorder: StatementRecorder,
    run_id: str = "",
    query_change_tracking: bool = False,
) -> SeedExecutionResult:
    """Load one seed into the warehouse."""

    start: float = time.monotonic()
    target_qualified: str = resolve_relation_location_qualified_name(
        adapter=adapter, location=seed_entry.destination
    )
    try:
        adapter.ensure_schema(
            connection=connection,
            database=seed_entry.destination.database,
            schema=seed_entry.destination.schema,
            statement_recorder=statement_recorder,
        )
        adapter.load_seed(
            connection=connection,
            destination=target_qualified,
            file_path=seed_entry.file_path,
            columns=seed_entry.columns,
            csv_settings=seed_entry.csv_settings,
            replace=True,
            statement_recorder=statement_recorder,
        )
        warnings: tuple[str, ...] = try_write_seed_fingerprint(
            seed_entry=seed_entry,
            adapter=adapter,
            connection=connection,
            run_id=run_id,
            query_change_tracking=query_change_tracking,
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
        warning_messages=warnings,
    )
