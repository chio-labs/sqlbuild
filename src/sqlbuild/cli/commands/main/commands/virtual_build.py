"""CLI orchestration for virtual-mode build."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.build.models import (
    VirtualBuildCliRequest,
    VirtualBuildExecution,
)
from sqlbuild.cli.commands._helpers.build.python_node_output import write_python_node_results
from sqlbuild.cli.commands._helpers.build.virtual_checks import run_post_virtual_build_checks
from sqlbuild.cli.commands._helpers.build.virtual_execution import execute_virtual_build
from sqlbuild.cli.commands._helpers.check.core import check_results_failed
from sqlbuild.cli.commands.classes.build_progress_callbacks import format_build_footer
from sqlbuild.cli.output.main.build_execution_json import format_build_execution_json
from sqlbuild.cli.output.main.write_execution_json_output import write_execution_json_output
from sqlbuild.cli.target_artifacts.main.write_python_check_runtime_target import (
    write_python_check_runtime_target,
)
from sqlbuild.cli.target_artifacts.main.write_runtime_target import write_runtime_target
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import PlanOutput
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

    execution: VirtualBuildExecution = execute_virtual_build(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        adapter_name=adapter_name,
        connection_config=connection_config,
        request=request,
        progress_stream=progress_stream,
    )
    result: VirtualBuildPipelineResult = execution.result
    stream: TextIO = execution.stream
    plan_output: PlanOutput = result.display_plan_output
    write_python_node_results(
        stream=stream,
        results=result.python_node_results,
        use_color=request.use_color,
    )
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
    stream.write("\n" + footer + "\n")
    stream.flush()
    write_execution_json_output(
        payload=format_build_execution_json(
            result=result.execution_result,
            plan=plan_output,
            python_node_results=result.python_node_results,
            python_check_results=check_results,
            command=request.execution_command,
        ),
        json_output=request.json_output,
        json_output_path=request.json_output_path,
    )
    return (
        0
        if result.execution_result.status == BuildStatus.SUCCESS
        and not check_results_failed(check_results)
        else 1
    )
