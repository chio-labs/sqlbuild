"""Scenario command runner."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.scenario.constants import FAILED_STATUS, SUCCESS_STATUS
from sqlbuild.cli.commands.main.helpers.scenario.selection import select_scenarios
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import ConnectionProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.planning_progress import PlanningProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.progress import format_build_header
from sqlbuild.cli.commands.main.shared.helpers.scenario_runtime_target_writer import (
    write_scenario_runtime_target,
)
from sqlbuild.cli.commands.main.shared.helpers.status import TransientStatusReporter
from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import ScenarioArtifactName, ScenarioExecutionPlan
from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.pipeline.main.run import (
    run_scenario_local_test_pipeline,
    run_scenario_test_pipeline,
)
from sqlbuild.executor.scenario.models import (
    ScenarioAssertionCheckExecutionResult,
    ScenarioExpectedCheckExecutionResult,
    ScenarioRunResult,
)
from sqlbuild.executor.scenario.types import ScenarioLocalRunStatus
from sqlbuild.shared.constants import SCENARIO_CLI_LOCAL_RETAIN_UNSUPPORTED
from sqlbuild.shared.helpers.coded_errors import format_coded_error
from sqlbuild.shared.helpers.colors import (
    blue_bold,
    colorize_status,
    dim,
    green_bold,
    supports_color,
)
from sqlbuild.spec.models.project import resolve_effective_adapter_name

_SCENARIO_NAME_WIDTH: int = 64
_CHECK_LABEL_WIDTH: int = 10
_CHECK_NAME_WIDTH: int = 50


def run_scenario(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    no_color: bool = False,
    selectors: tuple[str, ...] = (),
    retain: bool = False,
    local: bool = False,
    strict: bool = False,
) -> int:
    """Execute the scenario test command."""

    if local and retain:
        raise CliUserError(
            "scenario test --local does not support --retain",
            code=SCENARIO_CLI_LOCAL_RETAIN_UNSUPPORTED,
            help=("Local scenario DuckDB files are always kept under target/run/scenarios/."),
        )

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter_name: str = (
        "duckdb"
        if local
        else resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        )
    )
    adapter: BaseAdapter = resolve_adapter(adapter_name, project_dir=effective_project_dir)
    connection_config: dict[str, object] = (
        {"database": ":memory:"}
        if local
        else resolve_project_connection_config(
            discovered_inputs=discovered_inputs,
            project_dir=effective_project_dir,
        )
    )
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stdout
    target_label: str | None = " ".join(selectors) if selectors else None
    execution_header: str = format_build_header(
        command="sqb scenario test --local" if local else "sqb scenario test",
        target=target_label,
        concurrency=1,
    )
    execution_label: str = blue_bold("Execution") if use_color else "Execution"
    header_detail: str = dim(execution_header) if use_color else execution_header
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        use_color=use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    progress_stream.write(f"\n{execution_label}  {header_detail}\n\n")
    progress_stream.flush()

    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=True if local else no_sql_validation,
        connection_config=connection_config,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        on_progress=planning_progress.on_progress,
    )
    scenarios: tuple[CompiledSqlScenario, ...] = select_scenarios(
        project=pipeline_result.project,
        selectors=selectors,
        project_dir=effective_project_dir,
    )
    header: str = f"Scenario ({len(scenarios)} selected)"
    styled_header: str = green_bold(header) if use_color else header
    progress_stream.write(f"\n{styled_header}\n\n")
    progress_stream.flush()
    scenario_status: TransientStatusReporter = TransientStatusReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    status_is_tty: bool = hasattr(progress_stream, "isatty") and progress_stream.isatty()
    if not status_is_tty:
        progress_stream.write("Running scenarios...\n\n")
        progress_stream.flush()
    if local:
        results: tuple[ScenarioRunResult, ...] = run_scenario_local_test_pipeline(
            project_dir=effective_project_dir,
            pipeline_result=pipeline_result,
            scenarios=scenarios,
            adapter=adapter,
            project_name=discovered_inputs.project_config.name,
            strict=strict,
            on_scenario_start=lambda _scenario: (
                scenario_status.start("Running scenarios...") if status_is_tty else None
            ),
            on_scenario_complete=lambda _scenario, scenario_plan, result: _complete_scenario_run(
                scenario_status=scenario_status,
                status_is_tty=status_is_tty,
                target_dir=effective_project_dir / "target",
                adapter=adapter,
                scenario_plan=scenario_plan,
                result=result,
                progress_stream=progress_stream,
                use_color=use_color,
            ),
        )
    else:
        execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
            adapter_name=adapter_name,
            stream=progress_stream,
            use_color=use_color,
        )
        results = run_scenario_test_pipeline(
            pipeline_result=pipeline_result,
            scenarios=scenarios,
            connection_config=connection_config,
            adapter=adapter,
            project_name=discovered_inputs.project_config.name,
            retain=retain,
            on_connection_start=execution_connection_progress.on_connection_start,
            on_connection_complete=execution_connection_progress.on_connection_complete,
            on_connection_error=execution_connection_progress.on_connection_error,
            on_scenario_start=lambda _scenario: (
                scenario_status.start("Running scenarios...") if status_is_tty else None
            ),
            on_scenario_complete=lambda _scenario, scenario_plan, result: _complete_scenario_run(
                scenario_status=scenario_status,
                status_is_tty=status_is_tty,
                target_dir=effective_project_dir / "target",
                adapter=adapter,
                scenario_plan=scenario_plan,
                result=result,
                progress_stream=progress_stream,
                use_color=use_color,
            ),
        )
    scenario_status.close()

    if local:
        return _write_local_summary(results=results, stream=progress_stream)
    return _write_remote_summary(results=results, stream=progress_stream)


def _write_remote_summary(*, results: tuple[ScenarioRunResult, ...], stream: TextIO) -> int:
    pass_count: int = sum(1 for result in results if result.status == SUCCESS_STATUS)
    fail_count: int = len(results) - pass_count
    stream.write(f"\nPASS={pass_count}  FAIL={fail_count}  TOTAL={len(results)}\n")
    stream.flush()
    return 0 if fail_count == 0 else 1


def _write_local_summary(*, results: tuple[ScenarioRunResult, ...], stream: TextIO) -> int:
    pass_count: int = sum(
        1 for result in results if result.local_status == ScenarioLocalRunStatus.PASS
    )
    fail_count: int = sum(
        1 for result in results if result.local_status == ScenarioLocalRunStatus.FAIL
    )
    error_count: int = sum(
        1 for result in results if result.local_status == ScenarioLocalRunStatus.ERROR
    )
    skip_count: int = sum(
        1 for result in results if result.local_status == ScenarioLocalRunStatus.SKIP
    )
    stream.write(
        f"\nPASS={pass_count}  FAIL={fail_count}  ERROR={error_count}  "
        f"SKIP={skip_count}  TOTAL={len(results)}\n"
    )
    stream.flush()
    return 0 if fail_count == 0 and error_count == 0 else 1


def _complete_scenario_run(
    *,
    scenario_status: TransientStatusReporter,
    status_is_tty: bool,
    target_dir: Path,
    adapter: BaseAdapter,
    scenario_plan: ScenarioExecutionPlan | None,
    result: ScenarioRunResult,
    progress_stream: TextIO,
    use_color: bool,
) -> None:
    if status_is_tty:
        scenario_status.close()
    if scenario_plan is not None and result.local_status is None:
        write_scenario_runtime_target(
            target_dir=target_dir,
            adapter=adapter,
            scenario_plan=scenario_plan,
            result=result,
        )
    _write_scenario_result(result=result, stream=progress_stream, use_color=use_color)


def _write_scenario_result(*, result: ScenarioRunResult, stream: TextIO, use_color: bool) -> None:
    status_text: str = (
        result.local_status.value
        if result.local_status is not None
        else "PASS"
        if result.status == SUCCESS_STATUS
        else "FAIL"
    )
    status: str = colorize_status(status_text, use_color=use_color)
    stream.write(f"{result.scenario_name:<{_SCENARIO_NAME_WIDTH}} {status}\n")
    if result.error_message:
        rendered_error_message: str = _render_result_error(
            error_code=result.error_code,
            error_message=result.error_message,
            error_help=result.error_help,
        )
        error_line: str
        for error_line in rendered_error_message.splitlines():
            stream.write(f"    {error_line}\n")
        if not result.retained and result.local_status is None:
            stream.write("    Rerun with --retain to inspect scenario-owned artifacts.\n")
    _write_checks(result=result, stream=stream, use_color=use_color)
    if result.retained and result.relation_map is not None:
        stream.write("    Retained relations:\n")
        artifact: ScenarioArtifactName
        for artifact in result.relation_map.artifacts:
            kind: str = ScenarioArtifactKind(artifact.identity.kind).value
            stream.write(
                f"      {kind:<6} {artifact.identity.logical_name} -> {artifact.physical_name}\n"
            )
    if result.retained and result.local_duckdb_path is not None:
        stream.write(f"    Retained local DuckDB: {result.local_duckdb_path.as_posix()}\n")
    _write_check_failures(result=result, stream=stream)
    stream.flush()


def _write_checks(*, result: ScenarioRunResult, stream: TextIO, use_color: bool) -> None:
    expected: ScenarioExpectedCheckExecutionResult
    for expected in result.expected_results:
        status_text: str = "FAIL" if expected.status == FAILED_STATUS else "PASS"
        status: str = colorize_status(status_text, use_color=use_color)
        detail: str = ""
        if expected.status == FAILED_STATUS:
            detail = f"  {expected.mismatched_row_count} mismatched"
        item_name: str = f"expected {expected.model_name}"
        stream.write(
            f"    {'check':<{_CHECK_LABEL_WIDTH}}{item_name:<{_CHECK_NAME_WIDTH}} "
            f"{status}{detail}\n"
        )
        if expected.error_message is not None:
            rendered_error: str = _render_result_error(
                error_code=expected.error_code,
                error_message=expected.error_message,
                error_help=expected.error_help,
            )
            stream.write(f"{'':>14}{rendered_error}\n")
    assertion: ScenarioAssertionCheckExecutionResult
    for assertion in result.assertion_results:
        status_text = "FAIL" if assertion.status == FAILED_STATUS else "PASS"
        status = colorize_status(status_text, use_color=use_color)
        row_label: str = "row" if assertion.failing_row_count == 1 else "rows"
        detail = ""
        if assertion.status == FAILED_STATUS:
            detail = f"  {assertion.failing_row_count} {row_label}"
        item_name = f"assertion {assertion.name}"
        stream.write(
            f"    {'check':<{_CHECK_LABEL_WIDTH}}{item_name:<{_CHECK_NAME_WIDTH}} "
            f"{status}{detail}\n"
        )
        if assertion.error_message is not None:
            rendered_error = _render_result_error(
                error_code=assertion.error_code,
                error_message=assertion.error_message,
                error_help=assertion.error_help,
            )
            stream.write(f"{'':>14}{rendered_error}\n")


def _render_result_error(
    *, error_code: str | None, error_message: str, error_help: str | None = None
) -> str:
    if error_code is None:
        return error_message
    return format_coded_error(code=error_code, message=error_message, help=error_help)


def _write_check_failures(*, result: ScenarioRunResult, stream: TextIO) -> None:
    expected: ScenarioExpectedCheckExecutionResult
    for expected in result.expected_results:
        if expected.status != FAILED_STATUS:
            continue
        stream.write(
            f"    expected {expected.model_name}: actual={expected.actual_row_count} "
            f"expected={expected.expected_row_count} mismatched={expected.mismatched_row_count}\n"
        )
    assertion: ScenarioAssertionCheckExecutionResult
    for assertion in result.assertion_results:
        if assertion.status != FAILED_STATUS:
            continue
        stream.write(
            f"    assertion {assertion.name}: failing_rows={assertion.failing_row_count}\n"
        )
        if assertion.sample_rows:
            stream.write(f"    sample: {assertion.sample_rows[0]}\n")
