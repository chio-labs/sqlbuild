"""Helpers for external source loader execution."""

from __future__ import annotations

import logging
import time
from datetime import datetime

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.executor.load.models import LoaderContext, LoaderSkipResult, LoadExecutionResult
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.provider.main.runtime import ProviderContainer, invoke_with_providers
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.source import SourceEntry


def execute_external_source_load(
    *,
    source_entry: SourceEntry,
    loader_function: DiscoveredLoaderFunction,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    destination_relation: str,
    destination_name: str,
    run_id: str,
    target: str | None,
    vars: dict[str, object],
    is_reload: bool,
    start_cursor_ts: datetime | None,
    end_cursor_ts: datetime | None,
    start_cursor_int: int | None,
    end_cursor_int: int | None,
    statement_recorder: StatementRecorder,
    use_color: bool,
    resource_kind: ExecutionResourceKind,
    start: float,
    providers: ProviderContainer | None = None,
) -> LoadExecutionResult:
    """Run one external writer while SQLBuild holds no destination connection."""

    try:
        context: LoaderContext = LoaderContext(
            adapter=adapter,
            connection_config=connection_config,
            connection=None,
            destination=destination_relation,
            destination_database=source_entry.database,
            destination_schema=source_entry.schema,
            destination_name=destination_name,
            run_id=run_id,
            target=target,
            vars=vars,
            is_reload=is_reload,
            use_color=use_color,
            current_cursor_value=None,
            logger=logging.getLogger(f"sqlbuild.loader.{loader_function.name}"),
            statement_recorder=statement_recorder,
            start_cursor_ts=start_cursor_ts,
            end_cursor_ts=end_cursor_ts,
            start_cursor_int=start_cursor_int,
            end_cursor_int=end_cursor_int,
        )
        raw_rows: object = invoke_with_providers(
            function=loader_function.function,
            context=context,
            providers=providers,
        )
        if isinstance(raw_rows, LoaderSkipResult):
            return LoadExecutionResult(
                source_name=source_entry.name,
                loader_name=loader_function.name,
                status=ExecutionStatus.SKIPPED,
                target=destination_relation,
                resource_kind=resource_kind,
                staging_relation=None,
                rows_loaded=0,
                duration_ms=int((time.monotonic() - start) * 1000),
                lifecycle_events=statement_recorder.snapshot(),
                skip_mode=raw_rows.mode,
                skip_reason=raw_rows.reason,
            )
        if raw_rows is not None:
            raise ExecutorInputError(
                f"External loader '{loader_function.name}' returned rows, but external loaders "
                "must write their own destination and return None"
            )
        return LoadExecutionResult(
            source_name=source_entry.name,
            loader_name=loader_function.name,
            status=ExecutionStatus.SUCCESS,
            target=destination_relation,
            resource_kind=resource_kind,
            staging_relation=None,
            rows_loaded=0,
            duration_ms=int((time.monotonic() - start) * 1000),
            lifecycle_events=statement_recorder.snapshot(),
        )
    except Exception as error:
        return LoadExecutionResult(
            source_name=source_entry.name,
            loader_name=loader_function.name,
            status=ExecutionStatus.FAILED,
            target=destination_relation,
            resource_kind=resource_kind,
            staging_relation=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            lifecycle_events=statement_recorder.snapshot(),
            error_message=str(error),
        )
