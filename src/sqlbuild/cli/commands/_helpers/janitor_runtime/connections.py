"""Janitor command connection phases."""

from __future__ import annotations

import sys
import time

from sqlbuild.cli.commands.models import (
    JanitorCompileContext,
    JanitorConnectionContext,
    JanitorInvocation,
)
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


def connect_janitor_warehouse(
    *, invocation: JanitorInvocation, compile_context: JanitorCompileContext
) -> JanitorConnectionContext:
    """Connect to the janitor target warehouse."""

    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=compile_context.adapter_name,
        stream=sys.stdout,
        use_color=invocation.use_color,
    )
    connection_start: float = time.perf_counter()
    connection_progress.on_connection_start(1)
    try:
        with OperationLifecycle(
            operation_kind="janitor", operation_name="janitor_target_connection"
        ):
            connection: object = compile_context.adapter.connect(compile_context.connection_config)
    except BaseException:
        connection_progress.on_connection_error(
            connection_count=1, elapsed_seconds=time.perf_counter() - connection_start
        )
        raise
    connection_progress.on_connection_complete(
        connection_count=1, elapsed_seconds=time.perf_counter() - connection_start
    )
    return JanitorConnectionContext(connection=connection)


def close_janitor_warehouse(
    *, compile_context: JanitorCompileContext, connection_context: JanitorConnectionContext
) -> None:
    """Close the janitor warehouse connection."""

    compile_context.adapter.close(connection_context.connection)
