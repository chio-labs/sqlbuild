"""Runtime planning pipeline for `sqb dbt plan`."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.cli.commands.main.commands.connection_progress import (
    build_connection_progress_reporter,
)
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtInteropCompiledProject,
    DbtInteropExecutionRequest,
    DbtInteropInvocation,
    DbtInteropPlan,
    DbtInteropPlanResolution,
)
from sqlbuild.integrations.dbt.pipeline.helpers.execute import append_manifest_seed_warnings
from sqlbuild.integrations.dbt.pipeline.helpers.interop_prologue import (
    compile_dbt_interop_project,
    load_compiled_dbt_manifest,
    resolve_dbt_execution_invocation,
    resolve_dbt_interop_plan,
)
from sqlbuild.integrations.dbt.pipeline.helpers.plan_output import (
    apply_dbt_build_pruning,
    attach_dbt_model_plan,
    attach_sqlbuild_plan_output,
)
from sqlbuild.integrations.dbt.shared.helpers.progress import report_progress
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def plan_dbt_interop_from_project(
    *,
    project_dir: Path,
    args: tuple[str, ...],
    dbt_runner: DbtRunner | None = None,
    dbt_executable: str | None = None,
    sqlbuild_executable: str = "sqb",
    no_sql_validation: bool = False,
    on_progress: Callable[[str], None] | None = None,
    progress_stream: TextIO | None = None,
    use_color: bool = False,
) -> DbtInteropPlan:
    """Build a dbt interop plan from real project files and dbt artifacts."""

    invocation: DbtInteropInvocation = resolve_dbt_execution_invocation(
        DbtInteropExecutionRequest(
            command=DbtInteropCommand.PLAN,
            project_dir=project_dir,
            args=args,
            dbt_runner=dbt_runner,
            dbt_executable=dbt_executable,
            sqlbuild_executable=sqlbuild_executable,
            no_sql_validation=no_sql_validation,
            on_progress=on_progress,
            progress_stream=progress_stream,
            use_color=use_color,
        )
    )
    manifest: DbtManifestIndex = load_compiled_dbt_manifest(
        runner=invocation.runner,
        dbt_options=invocation.dbt_options,
        full_refresh=False,
        on_progress=on_progress,
    )
    compiled: DbtInteropCompiledProject = compile_dbt_interop_project(
        project_dir=project_dir,
        discovered_inputs=invocation.discovered_inputs,
        manifest=manifest,
        dbt_vars=invocation.dbt_vars,
        no_sql_validation=no_sql_validation,
        on_progress=on_progress,
    )
    connection_progress: Any | None = (
        build_connection_progress_reporter(
            adapter_name=compiled.adapter_name,
            stream=progress_stream,
            use_color=use_color,
        )
        if progress_stream is not None
        else None
    )
    generation_start: float = time.monotonic()
    resolution: DbtInteropPlanResolution = resolve_dbt_interop_plan(
        command=DbtInteropCommand.PLAN,
        invocation=invocation,
        compiled=compiled,
        manifest=manifest,
        sqlbuild_executable=sqlbuild_executable,
        on_progress=on_progress,
    )
    plan: DbtInteropPlan = attach_dbt_model_plan(
        plan=resolution.plan,
        project_dir=project_dir,
        discovered_inputs=invocation.discovered_inputs,
        compiled=compiled,
        manifest=manifest,
        graph=resolution.graph,
        full_refresh="--full-refresh" in invocation.routed.dbt_args,
        force=invocation.effective_force,
        connection_progress=connection_progress,
        on_progress=on_progress,
    )
    plan = append_manifest_seed_warnings(plan=plan, manifest=manifest)
    plan = apply_dbt_build_pruning(plan)
    plan = attach_sqlbuild_plan_output(
        plan=plan,
        project_dir=project_dir,
        discovered_inputs=invocation.discovered_inputs,
        compiled=compiled,
        manifest=manifest,
        graph=resolution.graph,
        sqlbuild_args=invocation.effective_sqlbuild_args,
        connection_progress=connection_progress,
        on_progress=on_progress,
    )
    report_progress(
        on_progress=on_progress,
        message=f"Generated dbt interop plan. ({time.monotonic() - generation_start:.2f}s)",
    )
    return plan
