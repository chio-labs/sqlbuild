"""CLI test command entry point."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.sql_test_progress import (
    build_test_expectation_rows,
    resolve_test_name_width,
)
from sqlbuild.cli.commands.main.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection.core import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands.main.shared.helpers.connection.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.main.shared.helpers.output.execution_json import (
    format_test_execution_json,
    write_execution_json_output,
)
from sqlbuild.cli.commands.main.shared.helpers.progress.connection import ConnectionProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.progress.core import write_execution_header
from sqlbuild.cli.commands.main.shared.helpers.progress.nested import NestedCommandProgressCallbacks
from sqlbuild.cli.commands.main.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.targets.runtime import (
    write_test_runtime_target,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import SqlTestPlanEntry
from sqlbuild.executor.pipeline.main.run import run_test_pipeline
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.shared.helpers.status import TransientStatusReporter
from sqlbuild.shared.helpers.summary_footer import format_summary_footer
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_test(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    no_color: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    cli_vars: dict[str, object] | None = None,
    json_output: bool = False,
    json_output_path: Path | None = None,
) -> int:
    """Execute the test command."""

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
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        stream=progress_stream,
        use_color=use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    progress_stream.write("\n")
    write_execution_header(
        stream=progress_stream,
        command="sqb test",
        target=None,
        concurrency=1,
        use_color=use_color,
    )
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        source_deferral_enabled=False,
        select=select,
        exclude=exclude,
        connection_config=connection_config,
        cli_vars=cli_vars,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        on_progress=planning_progress.on_progress,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
        ),
    )

    test_count: int = len(pipeline_result.plan_output.test_entries)
    model_count: int = len(
        {step.model_name for e in pipeline_result.plan_output.test_entries for step in e.chain}
    )
    header: str = f"Test ({test_count} selected, {model_count} models)"
    style: CliStyle = CliStyle(use_color=use_color)
    styled_header: str = style.success_strong(header)
    progress: NestedCommandProgressCallbacks = NestedCommandProgressCallbacks(
        total=test_count,
        label="test",
        stream=progress_stream,
        use_color=use_color,
        name_width=resolve_test_name_width(pipeline_result.plan_output.test_entries),
    )
    progress_stream.write(f"\n{styled_header}\n\n")
    progress_stream.flush()
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        stream=progress_stream,
        use_color=use_color,
    )
    preflight_progress: TransientStatusReporter = TransientStatusReporter(
        stream=progress_stream,
        use_color=use_color,
    )

    on_complete: Callable[[SqlTestExecutionResult], None] = _build_on_complete(progress=progress)
    preflight_active: list[bool] = [False]

    def on_test_progress(message: str) -> None:
        if message.startswith("Prepared "):
            preflight_progress.complete(message, blank_line_after=True)
            preflight_active[0] = False
            return
        if not preflight_active[0]:
            preflight_progress.start(message)
            preflight_active[0] = True
            return
        preflight_progress.update(message)

    results: tuple[SqlTestExecutionResult, ...] = run_test_pipeline(
        plan=pipeline_result.plan_output,
        connection_config=connection_config,
        adapter=adapter,
        on_connection_start=execution_connection_progress.on_connection_start,
        on_connection_complete=execution_connection_progress.on_connection_complete,
        on_connection_error=execution_connection_progress.on_connection_error,
        on_progress=on_test_progress,
        on_test_start=lambda entry: progress.on_item_start(
            group_name=_test_group_name_from_entry(entry),
            item_name=entry.name,
        ),
        on_test_complete=on_complete,
    )
    write_test_runtime_target(
        target_dir=effective_project_dir / "target",
        adapter=adapter,
        plan_output=pipeline_result.plan_output,
        results=results,
    )

    pass_count: int = sum(1 for r in results if r.outcome == SqlTestOutcome.PASS)
    fail_count: int = len(results) - pass_count
    progress_stream.write(
        "\n"
        + format_summary_footer(
            counts=(
                ("PASS", pass_count),
                ("FAIL", fail_count),
                ("TOTAL", len(results)),
            ),
            use_color=use_color,
        )
        + "\n"
    )
    progress_stream.flush()
    write_execution_json_output(
        payload=format_test_execution_json(results=results),
        json_output=json_output,
        json_output_path=json_output_path,
    )

    return 0 if fail_count == 0 else 1


def _build_on_complete(
    *, progress: NestedCommandProgressCallbacks
) -> Callable[[SqlTestExecutionResult], None]:
    def _on_complete(result: SqlTestExecutionResult) -> None:
        model_name: str = ""
        if result.step_results:
            model_name = result.step_results[0].model_name
        group_name: str = model_name or "(unknown)"
        status_text: str = "PASS" if result.outcome == SqlTestOutcome.PASS else "FAIL"
        progress.on_item_complete(
            group_name=group_name,
            item_name=result.test_name,
            status_text=status_text,
            child_rows=build_test_expectation_rows(result),
            error_code=result.error_code,
            error_help=result.error_help,
            error_message=result.error_message,
        )

    return _on_complete


def _test_group_name_from_entry(entry: SqlTestPlanEntry) -> str:
    if entry.chain:
        return entry.chain[0].model_name
    return "(unknown)"
