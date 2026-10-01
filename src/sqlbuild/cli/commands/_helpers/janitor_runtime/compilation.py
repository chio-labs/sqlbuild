"""Janitor command compilation phase."""

from __future__ import annotations

import sys
import time

from sqlbuild.cli.commands._helpers.runtime.adapter_context import (
    resolve_adapter_connection_context,
)
from sqlbuild.cli.commands.models import (
    AdapterConnectionContext,
    JanitorCompileContext,
    JanitorInvocation,
)
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.pipeline.main.project import compile_project
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


def compile_janitor_project(*, invocation: JanitorInvocation) -> JanitorCompileContext:
    """Compile for the janitor or ``--as`` target and resolve the active target connection."""

    adapter_context: AdapterConnectionContext = resolve_adapter_connection_context(
        discovered_inputs=invocation.discovered_inputs,
        effective_project_dir=invocation.effective_project_dir,
        selected_target=invocation.selected_target,
        cli_vars=None,
    )
    compile_start: float = time.perf_counter()
    status: PlanningProgressReporter = PlanningProgressReporter(
        stream=sys.stdout,
        use_color=invocation.use_color,
    )
    with OperationLifecycle(operation_kind="project", operation_name="project_compile"):
        status.on_progress("Compiling project...")
        project: CompiledProject = compile_project(
            discovered_inputs=invocation.discovered_inputs,
            adapter=adapter_context.adapter,
            selected_target=(
                invocation.as_target
                if invocation.as_target is not None
                else invocation.selected_target
            ),
            resolved_connection=adapter_context.connection_config,
        )
        status.on_progress(f"Compiled project. ({time.perf_counter() - compile_start:.2f}s)")
    return JanitorCompileContext(
        adapter_name=adapter_context.adapter_name,
        adapter=adapter_context.adapter,
        project=project,
        connection_config=adapter_context.connection_config,
    )
