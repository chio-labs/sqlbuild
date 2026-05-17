"""CLI seed command entry point."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.execution_json import (
    format_seed_execution_json,
    write_execution_json_output,
)
from sqlbuild.cli.commands.main.shared.helpers.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.build.types import ExecutionStatus
from sqlbuild.executor.pipeline.main.run import run_seed_pipeline
from sqlbuild.shared.helpers.coded_errors import format_coded_error
from sqlbuild.shared.helpers.colors import colorize_status, supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_seed(
    project_dir: Path | None,
    no_color: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    cli_vars: dict[str, object] | None = None,
    json_output: bool = False,
    json_output_path: Path | None = None,
) -> int:
    """Execute the seed command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter: BaseAdapter = resolve_adapter(
        resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project_dir=effective_project_dir,
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        cli_vars=cli_vars,
    )
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        select=select,
        exclude=exclude,
        connection_config=connection_config,
        cli_vars=cli_vars,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
        ),
    )

    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout
    progress_stream.write("sqb seed\n\n")
    progress_stream.flush()

    start: float = time.monotonic()
    on_complete: Callable[[SeedExecutionResult], None] = _build_on_complete(
        stream=progress_stream,
        use_color=use_color,
    )
    results: tuple[SeedExecutionResult, ...] = run_seed_pipeline(
        plan=pipeline_result.plan_output,
        connection_config=connection_config,
        adapter=adapter,
        on_seed_complete=on_complete,
    )
    elapsed: float = time.monotonic() - start

    success_count: int = sum(1 for r in results if r.status == ExecutionStatus.SUCCESS)
    fail_count: int = sum(1 for r in results if r.status == ExecutionStatus.FAILED)
    elapsed_str: str = f"{elapsed:.2f}s"
    completion: str = (
        colorize_status("OK", use_color=use_color)
        if fail_count == 0
        else colorize_status("FAIL", use_color=use_color)
    )
    progress_stream.write(
        f"\n{completion}  {success_count} loaded, {fail_count} failed  ({elapsed_str})\n"
    )
    progress_stream.flush()
    write_execution_json_output(
        payload=format_seed_execution_json(results=results, plan=pipeline_result.plan_output),
        json_output=json_output,
        json_output_path=json_output_path,
    )

    return 0 if fail_count == 0 else 1


def _build_on_complete(*, stream: TextIO, use_color: bool) -> Callable[[SeedExecutionResult], None]:
    def _on_complete(result: SeedExecutionResult) -> None:
        status_text: str = "OK" if result.status == ExecutionStatus.SUCCESS else "FAIL"
        status: str = colorize_status(status_text, use_color=use_color)
        duration: str = ""
        if result.duration_ms is not None:
            seconds: float = result.duration_ms / 1000.0
            duration = f"{seconds:.2f}s"
        stream.write(f"  {result.seed_name:<50} {status:<6} {duration}\n")
        if result.error_message is not None:
            stream.write(f"    {_format_seed_error(result=result, use_color=use_color)}\n")
        stream.flush()

    return _on_complete


def _format_seed_error(*, result: SeedExecutionResult, use_color: bool) -> str:
    if result.error_message is None:
        return ""
    if result.error_code is None:
        return result.error_message
    return format_coded_error(
        code=result.error_code,
        message=result.error_message,
        help=result.error_help,
        use_color=use_color,
    )
