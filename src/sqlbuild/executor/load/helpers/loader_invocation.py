"""Loader context construction and loader return-value interpretation."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.executor.load.helpers.relation_refs import (
    build_loader_relation_refs,
    build_source_relation_refs,
)
from sqlbuild.executor.load.models import (
    LoaderContext,
    LoaderDestination,
    LoaderRefBindings,
    LoaderResult,
    LoaderSkipResult,
    LoadExecutionResult,
    LoadRuntimeParams,
)
from sqlbuild.executor.node_results.models import NodeResultEnvelope
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.helpers.load_execution import (
    is_untargeted_self_managed_intermediate,
)
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.provider.main.runtime import _empty_provider_container
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.source import SourceEntry
from sqlbuild.spec.models.types import SourceWriteStrategy

_SUPPORTED_WRITE_STRATEGIES: frozenset[SourceWriteStrategy] = frozenset(
    {
        SourceWriteStrategy.APPEND,
        SourceWriteStrategy.DELETE_INSERT,
        SourceWriteStrategy.MERGE,
        SourceWriteStrategy.TABLE,
    }
)


def validate_source_write_strategy(source_entry: SourceEntry) -> None:
    """Reject write strategies that sqb load does not support."""

    if (
        source_entry.write_strategy is not None
        and source_entry.write_strategy not in _SUPPORTED_WRITE_STRATEGIES
    ):
        raise ExecutorInputError(
            f"Source '{source_entry.name}' uses write_strategy "
            f"'{source_entry.write_strategy}', "
            "but sqb load currently supports only write_strategy append, delete_insert, "
            "merge, and table"
        )


def build_loader_context(
    *,
    source_entry: SourceEntry,
    loader_function: DiscoveredLoaderFunction,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    destination: LoaderDestination,
    runtime: LoadRuntimeParams,
    statement_recorder: StatementRecorder,
    ref_bindings: LoaderRefBindings,
    on_progress: Callable[[str], None] | None,
) -> LoaderContext:
    """Assemble the runtime context handed to one loader function."""

    destination_relation: str = destination.relation
    destination_name: str = destination.name
    return LoaderContext(
        adapter=adapter,
        connection_config=connection_config,
        connection=connection,
        destination=destination_relation,
        destination_database=source_entry.database,
        destination_schema=source_entry.schema,
        destination_name=destination_name,
        run_id=runtime.run_id,
        runtime_dir=runtime.runtime_dir,
        target=runtime.target,
        vars=runtime.vars,
        is_reload=runtime.is_reload,
        use_color=runtime.use_color,
        current_cursor_value=_load_current_cursor_value(
            adapter=adapter,
            connection=connection,
            source_entry=source_entry,
            target=destination_relation,
            target_name=destination_name,
            statement_recorder=statement_recorder,
        ),
        logger=logging.getLogger(f"sqlbuild.loader.{loader_function.name}"),
        statement_recorder=statement_recorder,
        start_cursor_ts=runtime.start_cursor_ts,
        end_cursor_ts=runtime.end_cursor_ts,
        start_cursor_int=runtime.start_cursor_int,
        end_cursor_int=runtime.end_cursor_int,
        loader_refs=build_loader_relation_refs(
            adapter=adapter,
            connection=connection,
            entries=ref_bindings.loader_ref_entries or {},
            statement_recorder=statement_recorder,
        ),
        source_refs=build_source_relation_refs(
            adapter=adapter,
            connection=connection,
            entries=ref_bindings.source_ref_entries or {},
            statement_recorder=statement_recorder,
        ),
        providers=(
            runtime.providers if runtime.providers is not None else _empty_provider_container()
        ),
        result_store=runtime.result_store,
        on_progress=on_progress,
    )


def interpret_loader_return(
    *,
    raw_rows: object,
    source_entry: SourceEntry,
    loader_function: DiscoveredLoaderFunction,
    destination_relation: str,
    resource_kind: ExecutionResourceKind,
    statement_recorder: StatementRecorder,
    start: float,
) -> LoadExecutionResult | None:
    """Map non-row loader return values to results; None means rows follow."""

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
    if isinstance(raw_rows, LoaderResult):
        if source_entry.write_strategy is not None:
            raise ExecutorInputError(
                f"Managed source '{source_entry.name}' loader '{loader_function.name}' "
                "returned ctx.result(...); managed loaders must return dict rows "
                "or ctx.skip(...)"
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
            result_payload=raw_rows.payload,
            result_metadata=raw_rows.metadata,
            result_materialized=raw_rows.materialized,
        )
    if isinstance(raw_rows, NodeResultEnvelope):
        raise ExecutorInputError(
            f"Loader '{loader_function.name}' returned a node result envelope; "
            "use ctx.result(...) to return this loader's own result"
        )
    if raw_rows is None:
        if is_untargeted_self_managed_intermediate(
            source_entry=source_entry,
            loader_function=loader_function,
        ):
            raise ExecutorInputError(
                f"Loader '{loader_function.name}' returned no rows and has no destination declared"
            )
        if source_entry.write_strategy is not None:
            raise ExecutorInputError(
                f"Source '{source_entry.name}' defines write_strategy but loader "
                f"'{loader_function.name}' returned no rows"
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
    if source_entry.write_strategy is None:
        raise ExecutorInputError(
            f"Source '{source_entry.name}' loader '{loader_function.name}' returned rows "
            "but source has no write_strategy"
        )
    return None


def _load_current_cursor_value(
    *,
    adapter: BaseAdapter,
    connection: Any,
    source_entry: SourceEntry,
    target: str,
    target_name: str,
    statement_recorder: StatementRecorder,
) -> object | None:
    if source_entry.cursor_column is None:
        return None
    target_exists: bool = adapter.relation_exists(
        connection,
        database=source_entry.database,
        schema=source_entry.schema,
        name=target_name,
    )
    if not target_exists:
        return None
    sql: str = f"SELECT MAX({adapter.render_identifier(source_entry.cursor_column)}) FROM {target}"
    statement_recorder.record(sql)
    cursor: Any = adapter.execute(connection, sql)
    row: object | None = cursor.fetchone()
    if row is None:
        return None
    return row[0]
