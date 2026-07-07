"""Janitor command compilation phase."""

from __future__ import annotations

import sys
import time

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.janitor.models import (
    JanitorCompileContext,
    JanitorInvocation,
)
from sqlbuild.cli.commands.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.cli.commands.shared.helpers.connection.core import resolve_connection_config
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.pipeline.main.project import compile_project
from sqlbuild.shared.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def compile_janitor_project(*, invocation: JanitorInvocation) -> JanitorCompileContext:
    """Resolve adapter, compile project, and prepare connection config."""

    adapter_name: str = resolve_effective_adapter_name(
        project_config=invocation.discovered_inputs.project_config,
        local_config=invocation.discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name,
        project_dir=invocation.effective_project_dir,
    )
    compile_start: float = time.perf_counter()
    status: TransientStatusReporter = TransientStatusReporter(
        stream=sys.stdout,
        use_color=invocation.use_color,
    )
    status.start("Compiling project...")
    project: CompiledProject = compile_project(
        discovered_inputs=invocation.discovered_inputs,
        adapter=adapter,
    )
    status.complete(f"Compiled project. ({time.perf_counter() - compile_start:.2f}s)")
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=project.effective_connection,
        project_dir=invocation.effective_project_dir,
        adapter_name=adapter_name,
    )
    return JanitorCompileContext(
        adapter_name=adapter_name,
        adapter=adapter,
        project=project,
        connection_config=connection_config,
    )
