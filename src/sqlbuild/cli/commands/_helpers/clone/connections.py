"""Clone command connection phases."""

from __future__ import annotations

import time
from typing import Any

from sqlbuild.cli.commands._helpers.runtime.connection import (
    resolve_target_connection_config,
)
from sqlbuild.cli.commands.models import (
    CloneCommandRequest,
    CloneConnectionContext,
    CloneInvocation,
)
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter


def connect_clone_targets(
    *, request: CloneCommandRequest, invocation: CloneInvocation
) -> CloneConnectionContext:
    """Resolve connection configs and connect origin and destination targets."""

    origin_connection_config: dict[str, object] = resolve_target_connection_config(
        discovered_inputs=invocation.discovered_inputs,
        project_dir=invocation.effective_project_dir,
        target_name=request.origin_target_name,
        cli_vars=request.cli_vars,
    )
    destination_connection_config: dict[str, object] = resolve_target_connection_config(
        discovered_inputs=invocation.discovered_inputs,
        project_dir=invocation.effective_project_dir,
        target_name=invocation.destination_target_name,
        cli_vars=request.cli_vars,
    )
    progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
    )
    progress.start(f"Connecting to {invocation.adapter_name}...")
    connect_start: float = time.monotonic()
    origin_connection: Any = invocation.adapter.connect(origin_connection_config)
    destination_connection: Any = invocation.adapter.connect(destination_connection_config)
    progress.complete(
        f"Connected to {invocation.adapter_name}. ({time.monotonic() - connect_start:.2f}s)"
    )
    return CloneConnectionContext(
        origin_connection_config=origin_connection_config,
        destination_connection_config=destination_connection_config,
        origin_connection=origin_connection,
        destination_connection=destination_connection,
    )


def close_clone_targets(
    *, invocation: CloneInvocation, connection_context: CloneConnectionContext
) -> None:
    """Close origin and destination clone target connections."""

    invocation.adapter.close(connection_context.origin_connection)
    invocation.adapter.close(connection_context.destination_connection)
