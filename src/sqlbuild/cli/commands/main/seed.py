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
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import ConnectionProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.execution_json import (
    format_seed_execution_json,
    write_execution_json_output,
)
from sqlbuild.cli.commands.main.shared.helpers.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.main.shared.helpers.progress import write_execution_header
from sqlbuild.cli.commands.main.virtual_build import run_virtual_build
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.build.types import ExecutionStatus
from sqlbuild.executor.pipeline.main.run import run_seed_pipeline
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.provider.main.session import build_provider_session
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.coded_errors import format_coded_error
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.shared.helpers.summary_footer import format_summary_footer
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_seed(
    project_dir: Path | None,
    no_color: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    concurrency: int | None = None,
    cli_vars: dict[str, object] | None = None,
    json_output: bool = False,
    json_output_path: Path | None = None,
) -> int:
    """Execute the seed command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name,
        project_dir=effective_project_dir,
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        cli_vars=cli_vars,
    )
    use_color: bool = not no_color and supports_color()
    if discovered_inputs.project_config.settings.virtual_environments:
        provider_session: ProviderSession = build_provider_session(discovered_inputs.providers)
        try:
            return run_virtual_build(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
                adapter=adapter,
                adapter_name=adapter_name,
                connection_config=connection_config,
                include_python=False,
                seed_only=True,
                select=select,
                exclude=exclude,
                concurrency=concurrency,
                cli_vars=cli_vars,
                json_output=json_output,
                json_output_path=json_output_path,
                execution_command="seed",
                use_color=use_color,
                external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                    project_dir=effective_project_dir,
                    discovered_inputs=discovered_inputs,
                ),
                providers=provider_session.providers,
            )
        finally:
            provider_session.close()
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        use_color=use_color,
    )
    progress_stream.write("\n")
    progress_stream.flush()
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        select=select,
        exclude=exclude,
        connection_config=connection_config,
        cli_vars=cli_vars,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
        ),
    )

    effective_concurrency: int = max(
        1,
        concurrency if concurrency is not None else pipeline_result.project.settings.concurrency,
    )
    seed_count: int = len(pipeline_result.plan_output.seed_entries)
    style: CliStyle = CliStyle(use_color=use_color)
    ready_header: str = f"Seed ready ({seed_count} selected)"
    styled_ready_header: str = style.success_strong(ready_header)
    progress_stream.write(f"\n{styled_ready_header}\n\n")
    seeds_header: str = f"Seeds ({seed_count})"
    styled_seeds_header: str = style.success_strong(seeds_header)
    progress_stream.write(f"{styled_seeds_header}\n")
    for seed_entry in pipeline_result.plan_output.seed_entries:
        progress_stream.write(f"  {seed_entry.name}\n")
    progress_stream.write("\n")
    write_execution_header(
        stream=progress_stream,
        command="sqb seed",
        target=None,
        concurrency=effective_concurrency,
        use_color=use_color,
    )

    start: float = time.monotonic()
    on_complete: Callable[[SeedExecutionResult], None] = _build_on_complete(
        stream=progress_stream,
        use_color=use_color,
        seed_order={
            seed_entry.name: index
            for index, seed_entry in enumerate(pipeline_result.plan_output.seed_entries, start=1)
        },
        total_count=seed_count,
    )
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        blank_line_after_complete=True,
        use_color=use_color,
    )
    results: tuple[SeedExecutionResult, ...] = run_seed_pipeline(
        plan=pipeline_result.plan_output,
        connection_config=connection_config,
        adapter=adapter,
        max_concurrency=effective_concurrency,
        run_id=pipeline_result.project.run_id,
        query_change_tracking=pipeline_result.project.settings.query_change_tracking,
        on_seed_complete=on_complete,
        on_connection_start=execution_connection_progress.on_connection_start,
        on_connection_complete=execution_connection_progress.on_connection_complete,
        on_connection_error=execution_connection_progress.on_connection_error,
    )
    elapsed: float = time.monotonic() - start

    success_count: int = sum(1 for r in results if r.status == ExecutionStatus.SUCCESS)
    fail_count: int = sum(1 for r in results if r.status == ExecutionStatus.FAILED)
    elapsed_str: str = f"{elapsed:.2f}s"
    completion_message: str = (
        "Completed successfully." if fail_count == 0 else "Completed with errors."
    )
    progress_stream.write(f"\n{completion_message}\n")
    progress_stream.write(
        format_summary_footer(
            counts=(
                ("PASS", success_count),
                ("WARN", 0),
                ("FAIL", fail_count),
                ("SKIP", 0),
                ("TOTAL", len(results)),
            ),
            use_color=use_color,
            elapsed=elapsed_str,
        )
        + "\n"
    )
    progress_stream.flush()
    write_execution_json_output(
        payload=format_seed_execution_json(results=results, plan=pipeline_result.plan_output),
        json_output=json_output,
        json_output_path=json_output_path,
    )

    return 0 if fail_count == 0 else 1


def _build_on_complete(
    *,
    stream: TextIO,
    use_color: bool,
    seed_order: dict[str, int],
    total_count: int,
) -> Callable[[SeedExecutionResult], None]:
    def _on_complete(result: SeedExecutionResult) -> None:
        status_text: str = "OK" if result.status == ExecutionStatus.SUCCESS else "FAIL"
        style: CliStyle = CliStyle(use_color=use_color)
        status: str = style.status(status_text)
        duration: str = ""
        if result.duration_ms is not None:
            seconds: float = result.duration_ms / 1000.0
            duration = f"{seconds:.2f}s"
        ordinal: int = seed_order[result.seed_name]
        stream.write(
            f"  {ordinal}/{total_count}  seed      {result.seed_name:<30} {status:<6} {duration}\n"
        )
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
