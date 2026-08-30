"""Virtual clone command execution phase."""

from __future__ import annotations

import time

from sqlbuild.cli.commands._helpers.clone.virtual_output import (
    is_virtual_clone_success,
    render_virtual_clone_output,
)
from sqlbuild.cli.commands._helpers.planning.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands._helpers.runtime.connection import (
    resolve_target_connection_config,
)
from sqlbuild.cli.commands.models import CloneCommandRequest, CloneInvocation
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.virtual.executor.main.clone import run_virtual_clone
from sqlbuild.virtual.executor.models import CloneOptions, VirtualCloneResult


def execute_virtual_clone(*, request: CloneCommandRequest, invocation: CloneInvocation) -> int:
    """Run virtual clone and render its output."""

    progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
    )
    progress.start("Cloning virtual environment...")
    clone_start: float = time.monotonic()
    result: VirtualCloneResult = run_virtual_clone(
        project_dir=invocation.effective_project_dir,
        discovered_inputs=invocation.discovered_inputs,
        adapter=invocation.adapter,
        origin_target_name=request.origin_target_name,
        destination_target_name=invocation.destination_target_name,
        destination_connection_config=resolve_target_connection_config(
            discovered_inputs=invocation.discovered_inputs,
            project_dir=invocation.effective_project_dir,
            target_name=invocation.destination_target_name,
            cli_vars=request.cli_vars,
        ),
        options=CloneOptions(
            virtual_environment_name=request.virtual_env,
            skip_locked=request.skip_locked,
            no_sql_validation=request.no_sql_validation,
            select=request.select,
            exclude=request.exclude,
            cli_vars=request.cli_vars,
            external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                project_dir=invocation.effective_project_dir,
                discovered_inputs=invocation.discovered_inputs,
            ),
        ),
    )
    progress.complete(f"Cloned virtual environment. ({time.monotonic() - clone_start:.2f}s)")
    progress.finish(blank_line_after=True)
    render_virtual_clone_output(
        result=result,
        use_color=invocation.use_color,
        verbose=request.verbose,
    )
    return 0 if is_virtual_clone_success(result) else 1
