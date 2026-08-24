"""CLI orchestration for virtual-mode build."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.build_python_nodes.python_node_output import (
    write_python_node_results,
)
from sqlbuild.cli.commands._helpers.build_virtual.virtual_checks import (
    run_post_virtual_build_checks,
)
from sqlbuild.cli.commands._helpers.build_virtual.virtual_execution import execute_virtual_build
from sqlbuild.cli.commands._helpers.check.core import check_results_failed
from sqlbuild.cli.commands._helpers.cost.collection import (
    finalize_build_cost,
    render_build_cost,
)
from sqlbuild.cli.commands.classes.build_progress_callbacks import format_build_footer
from sqlbuild.cli.commands.classes.virtual_build_project_capture import (
    VirtualBuildProjectCapture,
)
from sqlbuild.cli.commands.models import (
    BuildCostFinalization,
    VirtualBuildCliRequest,
    VirtualBuildExecution,
)
from sqlbuild.cli.output.main._build_execution_json import format_build_execution_json
from sqlbuild.cli.output.main._write_execution_json_output import write_execution_json_output
from sqlbuild.cli.target_artifacts.main._write_python_check_runtime_target import (
    write_python_check_runtime_target,
)
from sqlbuild.cli.target_artifacts.main._write_runtime_target import write_runtime_target
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.plan_work import plan_has_executable_work
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.cost.classes.run_cost_store import RunCostStore
from sqlbuild.cost.models import CostRunRecord
from sqlbuild.cost.types import CostStatus
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.python_nodes.models import PythonCheckExecutionResult
from sqlbuild.virtual.executor.models import VirtualBuildPipelineResult


def run_virtual_build(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    adapter_name: str,
    connection_config: dict[str, object],
    request: VirtualBuildCliRequest,
    progress_stream: TextIO | None = None,
) -> int:
    """Execute a virtual build and render CLI output."""

    build_started_at: datetime = datetime.now(UTC)
    stream: TextIO = progress_stream or (
        sys.stderr if request.debug or request.json_output else sys.stdout
    )
    project_capture: VirtualBuildProjectCapture = VirtualBuildProjectCapture()

    def persist_started_cost(project: CompiledProject) -> None:
        project_capture.capture(project)
        try:
            _ = _persist_virtual_started_cost(
                project_dir=project_dir,
                discovered_inputs=discovered_inputs,
                adapter=adapter,
                adapter_name=adapter_name,
                connection_config=connection_config,
                project=project,
                stream=stream,
                started_at=build_started_at,
                use_color=request.use_color,
            )
        except BaseException:
            return

    try:
        execution: VirtualBuildExecution = execute_virtual_build(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            adapter_name=adapter_name,
            connection_config=connection_config,
            request=request,
            progress_stream=stream,
            on_project_ready=persist_started_cost,
        )
        result: VirtualBuildPipelineResult = execution.result
        return _complete_virtual_build(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            adapter_name=adapter_name,
            connection_config=connection_config,
            request=request,
            execution=execution,
            result=result,
            stream=stream,
            build_started_at=build_started_at,
        )
    except BaseException as error:
        compiled_project: CompiledProject | None = project_capture.project
        if compiled_project is None:
            raise
        interrupted: bool = isinstance(error, KeyboardInterrupt)
        try:
            _ = finalize_build_cost(
                BuildCostFinalization(
                    project_dir=project_dir,
                    adapter_name=adapter_name,
                    adapter=adapter,
                    connection_config=connection_config,
                    target_name=compiled_project.effective_target_name,
                    run_id=compiled_project.run_id,
                    build_status="interrupted" if interrupted else "failed",
                    started_at=build_started_at,
                    completed_at=datetime.now(UTC),
                    config=discovered_inputs.project_config.cost,
                    output_stream=stream,
                    use_color=request.use_color,
                    collect=not interrupted,
                    render=False,
                    cost_status=CostStatus.PARTIAL,
                    cost_message="Build was interrupted before cost collection completed.",
                )
            )
        except BaseException:
            pass
        raise


def _complete_virtual_build(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    adapter_name: str,
    connection_config: dict[str, object],
    request: VirtualBuildCliRequest,
    execution: VirtualBuildExecution,
    result: VirtualBuildPipelineResult,
    stream: TextIO,
    build_started_at: datetime,
) -> int:
    plan_output: PlanOutput = result.display_plan_output
    write_python_node_results(
        stream=stream,
        results=result.python_node_results,
        use_color=request.use_color,
    )
    with CostContext.scope(
        run_id=result.project.run_id,
        resource_type="run",
        resource_name=result.project.effective_target_name or adapter_name,
        ledger_path=project_dir / "target" / "runs" / result.project.run_id / "statements.jsonl",
        phase="post_build_checks",
    ):
        check_results: tuple[PythonCheckExecutionResult, ...] = run_post_virtual_build_checks(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            connection_config=connection_config,
            result=result,
            exclude=request.exclude,
            reload_sources=request.reload_sources,
            providers=request.providers,
            stream=stream,
            use_color=request.use_color,
        )
    build_completed_at: datetime = datetime.now(UTC)
    footer: str = format_build_footer(
        result=result.execution_result,
        elapsed=execution.elapsed,
        use_color=request.use_color,
        python_node_results=result.python_node_results,
    )
    write_runtime_target(
        target_dir=project_dir / "target",
        plan_output=plan_output,
        result=result.execution_result,
    )
    write_python_check_runtime_target(target_dir=project_dir / "target", results=check_results)
    exit_code: int = (
        0
        if result.execution_result.status == BuildStatus.SUCCESS
        and not check_results_failed(check_results)
        else 1
    )
    had_executable_work: bool = bool(result.python_node_results) or plan_has_executable_work(
        plan=result.execution_plan,
        python_plan_entries=(),
    )
    cost_record: CostRunRecord | None = finalize_build_cost(
        BuildCostFinalization(
            project_dir=project_dir,
            adapter_name=adapter_name,
            adapter=adapter,
            connection_config=connection_config,
            target_name=result.project.effective_target_name,
            run_id=result.project.run_id,
            build_status="success" if exit_code == 0 else "failed",
            started_at=build_started_at,
            completed_at=build_completed_at,
            config=discovered_inputs.project_config.cost,
            output_stream=stream,
            use_color=request.use_color,
            collect=had_executable_work,
            render=False,
            had_executable_work=had_executable_work,
        )
    )
    stream.write("\n" + footer + "\n")
    stream.flush()
    write_execution_json_output(
        payload=format_build_execution_json(
            result=result.execution_result,
            plan=plan_output,
            python_node_results=result.python_node_results,
            python_check_results=check_results,
            command=request.execution_command,
            run_id=None if cost_record is None else result.project.run_id,
            cost=(None if cost_record is None else RunCostStore.output_payload(record=cost_record)),
        ),
        json_output=request.json_output,
        json_output_path=request.json_output_path,
    )
    _ = render_build_cost(
        record=cost_record,
        output_stream=stream,
        use_color=request.use_color,
    )
    return exit_code


def _persist_virtual_started_cost(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    adapter_name: str,
    connection_config: dict[str, object],
    project: CompiledProject,
    stream: TextIO,
    started_at: datetime,
    use_color: bool,
) -> None:
    _ = finalize_build_cost(
        BuildCostFinalization(
            project_dir=project_dir,
            adapter_name=adapter_name,
            adapter=adapter,
            connection_config=connection_config,
            target_name=project.effective_target_name,
            run_id=project.run_id,
            build_status="running",
            started_at=started_at,
            completed_at=started_at,
            config=discovered_inputs.project_config.cost,
            output_stream=stream,
            use_color=use_color,
            collect=False,
            render=False,
            cost_status=CostStatus.PENDING,
            cost_message="Build cost collection has not completed.",
        )
    )
